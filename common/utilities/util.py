import Cookie
import errno
import random
import logging
import traceback
import socket
import os

from common import constants

STATUS_CODES = {
    200: "OK",
    307: "Temporary Redirect",
    401: "Unauthorized",
    404: "File Not Found",
    500: "Internal Error",
}


class HTTPError(RuntimeError):
    def __init__(
        self,
        code,
        status,
        message="",
    ):
        super(HTTPError, self).__init__(message)
        self.code = code
        self.status = status
        self.message = message


class FDOpen(object):
    def __init__(
        self,
        file,
        flags,
        mode=None,
    ):
        self._file = file
        self._flags = flags
        self._mode = mode

    def __enter__(self):
        self._fd = None
        self.fd = None
        if self._mode:
            self._fd = self.fd = os.open(
                self._file,
                self._flags,
                self._mode,
            )
        else:
            self._fd = self.fd = os.open(
                self._file,
                self._flags,
            )
        return self.fd

    def __exit__(self, type, value, traceback):
        if self._fd:
            os.close(self._fd)


class Disconnect(RuntimeError):
    def __init__(self, desc="Disconnect"):
        super(Disconnect, self).__init__(desc)


def text_to_html(
    text,
):
    return ("<HTML>\r\n<BODY>\r\n%s\r\n</BODY>\r\n</HTML>" % text)


def text_to_css(
    text,
    error=False,
):
    return (
        constants.RESPONSE_CSS +
        '<h1 %s>%s</h1>' % ('class="error"' * error, text) +
        constants.BACK_TO_MENU
    )


def random_cookie():
    result = ""
    for i in range(0, 64):
        result += str(random.randint(0, 255))
    return result


def parse_cookies(string, cookie):
    if string is None:
        return None
    c = Cookie.SimpleCookie()
    c.load(string)
    if c.get(cookie) is None:
        return None
    return c.get(cookie).value


def parse_header(line):
    SEP = ':'
    n = line.find(SEP)
    if n == -1:
        raise RuntimeError('Invalid header received')
    return line[:n].rstrip(), line[n + len(SEP):].lstrip()


def recv_line(
    buffer
):
    n = buffer.find(constants.CRLF_BIN)
    if n == -1:
        return None, buffer

    result = buffer[:n]
    buffer = buffer[n + len(constants.CRLF_BIN):]
    return result, buffer


def get_headers(
    request_context,
):
    finished = False
    for i in range(constants.MAX_NUMBER_OF_HEADERS):
        line, request_context["recv_buffer"] = recv_line(
            request_context["recv_buffer"])
        if line is None:  # means that async server has yet to receive all headers
            break
        if line == "":  # this is the end of headers
            finished = True
            break
        line = parse_header(line)
        if line[0] in request_context["req_headers"]:
            request_context["req_headers"][line[0]] = line[1]
    else:
        raise RuntimeError("Exceeded max number of headers")
    return finished


def send_headers(
    request_context,
):
    for key, value in request_context["headers"].iteritems():
        request_context["send_buffer"] += (
            "%s: %s\r\n" % (key, value)
        )
    request_context["send_buffer"] += ("\r\n")
    return True


def receive_buffer(entry):
    free_buffer_size = constants.BLOCK_SIZE - len(
        entry.request_context["recv_buffer"]
    )
    try:
        t = entry.socket.recv(free_buffer_size)
        if not t:
            raise Disconnect(
                'Disconnected while recieving content'
            )
        entry.request_context["recv_buffer"] += t
    except socket.error as e:
        traceback.print_exc()
        if e.errno not in (errno.EAGAIN, errno.EWOULDBLOCK):
            raise


def add_status(entry, code, extra):
    if not entry.request_context.get("status_sent"):
        entry.request_context["code"] = code
        entry.request_context["status"] = STATUS_CODES.get(code, 500)
    else:
        entry.request_context["send_buffer"] += ((
            "%s %s %s\r\n"
        ) % (
            constants.HTTP_SIGNATURE,
            code,
            STATUS_CODES[code],
        )
        ).encode("utf-8")

def random_pad(data, length):
    b = bytearray(data)
    b += os.urandom(length - len(b))
    return b