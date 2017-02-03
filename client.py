#!/usr/bin/python
import argparse
import contextlib
import logging
import socket

import constants

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dst-address",
        default="0.0.0.0",
        help="Server bind address. Default: %(default)s",
    )
    parser.add_argument(
        "--dst-port",
        type=int,
        default=8888,
        help="Initial server bind port. Default: %(default)s",
    )
    parser.add_argument(
        "--action",
        choices=["read", "write"],
        default="read",
        help="Whether to read or write from block device",
    )
    parser.add_argument(
        "--block",
        type=int,
        default=0,
        help="Which block to read/write from",
    )
    args = parser.parse_args()
    return args

def send_string(socket, string):
    while string:
        string = string[socket.send(string):]

def main():
    args = parse_args()
    logging.basicConfig(filename=None, level=logging.DEBUG)

    with contextlib.closing(
        socket.socket(
            family=socket.AF_INET,
            type=socket.SOCK_STREAM,
        )
    ) as s:
        s.connect((args.dst_address, args.dst_port))
        s.settimeout(1)
        if args.action == "read":
            cmd = "GET /%s?block=%d %s\r\n\r\n" % (
                args.action,
                args.block,
                constants.HTTP_SIGNATURE
            )
            send_string(s, cmd)
        data = s.recv(constants.BLOCK_SIZE)
        while data:
            logging.debug(data)
            data = s.recv(constants.BLOCK_SIZE)

main()
