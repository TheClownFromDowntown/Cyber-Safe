#!/usr/bin/python
## @package frontend.__main__
# main program of frontend HTTP server.
## @file frontend/__main__.py Implementation of @ref frontend.__main__
import argparse
import ConfigParser
import logging
import multiprocessing
import os
import resource
import signal

from common import async_server
from common import constants
from common import event_object
from common.utilities import util
from common.pollables.http_socket import HttpSocket

## Daemon function.
# when called, makes the program run in the background as a daemon process.
def daemonize():
    os.closerange(3, resource.RLIMIT_NOFILE)
    child = os.fork()
    if child != 0:
        os._exit(0)

    signal.signal(signal.SIGHUP, signal.SIG_IGN)

    null = os.open(os.devnull, os.O_RDWR)
    for i in range(0, 3):
        os.dup2(null, i)
    os.close(null)

## Parse args function.
# uses argparse module to parse arguments on server startup.
# @returns (dict) arguments and their values.
def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--max-connections",
        type=int,
        default=10,
        help="Number of connections the server accepts. Default: %(default)s",
    )
    parser.add_argument(
        "--log-file",
        default=None,
        help="Optional file to log into",
    )
    parser.add_argument(
        "--base",
        default=constants.BASE,
        help="base location of files",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=1,
        help="Optional server polling timeout",
    )
    parser.add_argument(
        "--foreground",
        action="store_true",
        default=False,
        help="Whether to daemonize program. Default: %(default)s",
    )
    parser.add_argument(
        "--event-method",
        help="whether to use select instead of poll. Default: %s" % (
            "select" if os.name == "nt" else "poll"
        ),
        choices=["select", "poll"],
        default="select" if os.name == "nt" else "poll"
    ),
    parser.add_argument(
        "--config",
        help="path for the config file",
        default="frontend/config.ini"
    )

    args = parser.parse_args()
    args.base = os.path.normpath(os.path.realpath(args.base))
    return args

## Main function.
# initializes all arguments and configurations into application context.
# creates an asynchronous server with a listener and calls run() on it.
def __main__():
    args = parse_args()
    if args.foreground:
        daemonize()

    logging.basicConfig(filename=args.log_file, level=logging.DEBUG)

    Config = ConfigParser.ConfigParser()
    Config.read(args.config)


    devices = None
    bind_address = Config.get('frontend', 'bind.address')
    bind_port = Config.getint('frontend', 'bind.port')
    devices = {}
    for i in Config.sections():
        if Config.has_option(i, "bd_identifier"):
            devices[i] = {
                "address": Config.get(i, "address"),
                "port": Config.getint(i, "port"),
                "username": Config.get(i, "username"),
                "password": Config.get(i, "password"),
            }
    sparse = None
    admin = Config.get('frontend', 'admin.password')

    objects = []

    def terminate(signum, frame):
        for o in objects:
            o.stop(signum, frame)

    signal.signal(signal.SIGINT, terminate)
    signal.signal(signal.SIGTERM, terminate)

    poll_object = {
        "poll": event_object.PollEvents,
        "select": event_object.SelectEvents,
    }[args.event_method]

    app_context = {
        "log": args.log_file,
        "event_object": poll_object,
        "bind_address": bind_address,
        "bind_port": bind_port,
        "timeout": args.timeout,
        "max_connections": args.max_connections,
        "sparse": sparse,
        "block_device": False,
        "devices": devices,
        "config": Config,
        "admin": admin,
        "base": args.base,
        "password_dict": {},
        "semaphore": multiprocessing.BoundedSemaphore(constants.MAX_SEMAPHORE),
    }

    server = async_server.Server(
        app_context,
    )
    server.add_listener(
        bind_address,
        bind_port,
        HttpSocket,
    )

    objects.append(server)
    logging.debug("main module called - server.run()")
    server.run()


if __name__ == "__main__":
    __main__()
