#!/usr/bin/env python3

import fcntl
import json
import logging
import os
import signal
import sys
import inspect
import types

from datetime import datetime
from functools import wraps
from math import floor
from time import sleep, time


# Logging
def init_logger():
    MAIN_NAME = os.path.splitext(os.path.basename(sys.modules["__main__"].__file__))[0]
    logger = logging.getLogger(MAIN_NAME)
    return logger


class KillHandler:
    kill_now = False

    def __init__(self):
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)

    def exit_gracefully(self, signum, frame):
        self.kill_now = True


def first(iter):
    return iter[0]


def deflogger(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        # if TRACE: print ("[@deflogger] {} (args: {}, kwargs:{})".format (func.__name__, args, kwargs))
        # TRACE = kwargs['TRACE'] if kwargs['TRACE'] else False
        # print (kwargs)
        if TRACE:
            logger.debug("[@deflogger] {}".format(func.__name__))
        return func(*args, **kwargs)

    return wrapper


def prettyprint_request(req):
    """
    At this point it is completely built and ready
    to be fired; it is "prepared".

    However pay attention at the formatting used in
    this function because it is programmed to be pretty
    printed and may differ from the actual request.
    """
    print(
        "{}\n{}\n{}\n\n{}\n{}\n".format(
            "-----------<prettyprint_request>-----------",
            req.method + " " + req.url,
            "\n".join("{}: {}".format(k, v) for k, v in req.headers.items()),
            req.body,
            "-----------</prettyprint_request>-----------",
        )
    )


def dry_request(url, headers, method=None, payload=None):
    print(
        "[dryrun] would send request:\n",
        json.dumps(
            {"url": url, "method": method, "headers": headers, "payload": payload},
            sort_keys=False,
            ensure_ascii=False,
        ),
    )


def debugtest01():
    print("test ok")


def measure(operation=sum):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            t = time()
            result = func(*args, **kwargs)
            ttr = time() - t
            # delays.append( {'func':func.__name__, 'args': args, 'kwargs':kwargs, 'ttr':ttr})
            key = func.__module__ + "." + func.__name__
            delays[key] = operation((ttr, delays.get(key, 0)))
            if TRACE:
                logger.debug(
                    "[@measure({0})] {1} took: {2:.2f} s".format(
                        operation.__name__, key, ttr
                    )
                )
            return result

        return wrapper

    return decorator


def run_once(main):
    global fh
    # fh=open(os.path.realpath(__file__),'r')
    fh = open(main, "r")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except BlockingIOError:
        return False


def get_uptime():
    return (datetime.now() - START_TIME).total_seconds()


def handle_exception(exc_type, exc_value, exc_traceback):
    """ # add sys.excepthook = handle_exception to main.py"""
    if issubclass(exc_type, KeyboardInterrupt):
        logger.warning("Interrupted.")
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    logger.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))
    logger.info("Terminating..")
    sys.exit(255)


def debug_exception(type, value, tb):
    """ # add sys.excepthook = debug_exception to main.py"""
    if hasattr(sys, 'ps1') or not sys.stderr.isatty():
        # we are in interactive mode or we don't have a tty-like
        # device, so we call the default hook
        sys.__excepthook__(type, value, tb)
    else:
        import traceback, pdb
        # we are NOT in interactive mode, print the exception...
        traceback.print_exception(type, value, tb)
        print
        # ...then start the debugger in post-mortem mode.
        pdb.post_mortem(tb)


def crash_me():
    print(2 / 0)


def killer_loop(killer, loops, period, exit):
    i = 0
    while (i := i + 1) and (i <= loops or loops == -1):
        loop_start_time = datetime.now()
        if DEBUG:
            logger.debug(f"Loop {i}.")

        # main executes here
        yield i

        # loop_end_time = datetime.now()
        if TRACE:
            logger.debug(f"Loop {i} ended, sleeping..")
        if loops != 1:
            killer_sleep(killer=killer, start_time=loop_start_time, period=period, exit=exit)


def killer_sleep(killer, start_time, period, exit):
    stop_time = datetime.now()
    load_time = (stop_time - start_time).total_seconds()
    sleep_time_total = period - load_time
    sleep_time_approx = 0.3  # seconds
    sleep_cycles = floor(sleep_time_total / sleep_time_approx)
    # forced sleep to allow for interrupting
    if sleep_cycles > 0:
        sleep_time = sleep_time_total / sleep_cycles
    else:
        sleep_cycles = sleep_time = 1
    #logger.debug(f"{load_time=}, {sleep_cycles=}, {sleep_time=}")

    for c in range(0, sleep_cycles):
        if killer.kill_now:
            logger.info("Stopping..")
            if exit:
                sys.exit(1)
        sleep(sleep_time)


def deflogger_module(module, decorator_def, decorator_class=None):
    for name, member in inspect.getmembers(module):
        if inspect.getmodule(member) == module and callable(member):
            if member == deflogger_module or member == decorator_def:
                continue
            if isinstance(member, types.FunctionType):
                module.__dict__[name] = decorator_def(member)
            elif decorator_class:
                module.__dict__[name] = decorator_class(member)


def deflogger_class(cls):
    for attr in cls.__dict__:
        if callable(getattr(cls, attr)):
            setattr(cls, attr, deflogger(getattr(cls, attr)))
    return cls


fh = 0

delays = {}

START_TIME = datetime.now()

TRACE = False
DRYRUN = False
DEBUG = False
LOGLEVEL = logging.INFO

logger = init_logger()
logger.debug(f'{__name__} init done.')
