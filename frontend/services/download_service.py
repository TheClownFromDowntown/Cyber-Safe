#!/usr/bin/python
import struct
import logging
import urlparse

import pyaes

from common import constants
from common.utilities import util
from common.utilities import encryption_util
from common.utilities.util import HTTPError
from common.root_entry import RootEntry
from common.services.service_base import ServiceBase
from common.utilities import block_util


class Download(ServiceBase):
    @staticmethod
    def name():
        return "/download"

    def before_request_content(
        self,
        request_context,
    ):
        self._authorization = self.get_authorization(request_context)
        qs = urlparse.parse_qs(request_context["parsed"].query)
        if not qs.get("filename"):
            request_context["headers"][constants.CONTENT_TYPE] = "text/html"
            raise util.HTTPError(500, "Internal Error", util.text_to_css(
                "File name missing", error=True))
        request_context["file_name"] = str(qs["filename"][0])
        self._parse_core(
            request_context,
            self._after_root,
        )

    def _after_root(
        self,
        request_context,
    ):
        index = 0
        main_num = None
        while index < len(self._root):
            # check if entry is the file
            entry = RootEntry()
            entry.load_entry(
                self._root[
                    index: index + constants.ROOT_ENTRY_SIZE
                ],
            )
            index += constants.ROOT_ENTRY_SIZE
            if entry.is_empty():
                continue
            if entry.compare_sha(
                user_key=encryption_util.sha(self._authorization)[:16],
                file_name=request_context["file_name"]
            ):
                main_num = entry.main_block_num
                encrypted = entry.get_encrypted(
                    user_key=encryption_util.sha(self._authorization)[:16],
                )
                request_context["headers"][constants.CONTENT_LENGTH] = encrypted["file_size"]
                self._file_size = encrypted["file_size"] # save for later use
                break
        if main_num is None:
            raise HTTPError(
                500,
                "Internal Error",
                "File %s does not exist" %
                request_context["file_name"])
        block_util.bd_action(
            request_context=request_context,
            block_num=main_num,
            action=constants.READ,
            service_wake_up=self._handle_main_block,
        )

    def _handle_main_block(
        self,
        request_context,
    ):
        self._main_block = request_context["block"]
        self._main_index = 0
        self._dir_index = 0
        self._dir_block = None

    def _handle_dir_block(
        self,
        request_context,
    ):
        self._dir_block = request_context["block"]
        self._dir_index = 0

    def _handle_block(
        self,
        request_context,
    ):
        # decrypt block using user key
        iv = request_context["block"][:16]
        request_context["block"] = request_context["block"][16:]
        key = encryption_util.sha(self._authorization)[:16]
        aes = pyaes.AESModeOfOperationCBC(key, iv=str(iv))
        request_context["block"] = encryption_util.decrypt_block_aes(
            block=request_context["block"],
            aes=aes,
        )
        request_context["block"] = request_context["block"][:self._file_size] # cut padding files
        self._file_size -= len(request_context["block"])
        # send block to user
        request_context["response"] = request_context["block"]
        request_context["block"] = ""

    def before_response_headers(
        self,
        request_context,
    ):
        file_type = request_context["file_name"].split(".")
        if len(file_type) == 1:
            file_type.append("*")
        request_context["headers"][constants.CONTENT_TYPE] = constants.MIME_MAPPING.get(
            file_type[1], constants.MIME_MAPPING["*"], )
        request_context["headers"]["Content-Disposition"] = (
            "attachment; filename=%s" % request_context["file_name"]
        )

    def _next_dir_block(
        self,
        request_context,
    ):
        current_block_num = struct.unpack(
            ">I",
            self._main_block[self._main_index: self._main_index + 4]
        )[0]
        self._main_index += 4
        block_util.bd_action(
            request_context=request_context,
            block_num=current_block_num,
            action=constants.READ,
            service_wake_up=self._handle_dir_block,
        )
        return current_block_num

    def response(
        self,
        request_context,
    ):
        if self._file_size == 0:
            return None # finished if entire file sent
        if self._dir_block is None or self._dir_index >= len(self._dir_block):
            # get next dir_block
            self._next_dir_block(request_context)
            return constants.RETURN_AND_WAIT
        else:
            current_block_num = struct.unpack(
                ">I",
                self._dir_block[self._dir_index: self._dir_index + 4],
            )[0]
            block_util.bd_action(
                request_context=request_context,
                block_num=current_block_num,
                action=constants.READ,
                service_wake_up=self._handle_block,
            )
            self._dir_index += 4
            return constants.RETURN_AND_WAIT
