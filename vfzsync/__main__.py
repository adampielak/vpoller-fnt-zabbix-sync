#!/usr/bin/env python3

import atexit
import json
import logging
import logging.config
import os
import sys
import time

import vfzsync.lib.vfzlib
import vfzsync
import debugtoolkit.debugtoolkit as debugtoolkit
from vfzsync import init_logging
from debugtoolkit.debugtoolkit import (crash_me, deflogger, measure, handle_exception,
                                       deflogger_module)
from vfzsync.lib.vfzlib import (test_config, VFZSync)

# import dryable
# import http.client
# http.client.HTTPConnection.debuglevel = 1
# from urllib3.exceptions import HTTPError as BaseHTTPError


def exit_process():
    if debugtoolkit.TRACE:
        logger.debug("DEBUG summary:")
        if "stats" in globals() and stats:
            logger.debug("[stats]\n", json.dumps(stats, indent=4, sort_keys=False))
        logger.debug(f"[uptime] {debugtoolkit.get_uptime():.2f} s")
        logger.debug("[@measure] summary:")
        for dly in debugtoolkit.delays:
            logger.debug(f"{dly}\t {debugtoolkit.delays[dly]:.2f} \ts")

    logger.info("Stopped.")


def script_main():
    # test_config()

    # debugtoolkit.crash_me()
    try:
        vfzsync = VFZSync()
    except Exception:
        logger.exception(f"Failed to initialize vfzsync.")
        sys.exit(3)

    for i in debugtoolkit.killer_loop(killer, CONFIG["general"]["loops"], CONFIG["general"]["interval"], exit=True):
        vfzsync.run_sync()


# globals


CONFIG = vfzsync.CONFIG

# dryable.set(False)


if __name__ == "__main__":
    # Flow control
    debugtoolkit.DEBUG = CONFIG["general"]["debug"]
    debugtoolkit.TRACE = CONFIG["general"]["trace"]
    debugtoolkit.DRYRUN = CONFIG["general"]["dryrun"]

    # Logging
    # logger, LOG_FILE = init_logging()
    
    NAME_NOEXT = os.path.splitext(os.path.basename(__file__))[0]

    logger = logging.getLogger(NAME_NOEXT)
    LOG_FILE = [handler.baseFilename for handler in logger.handlers if type(handler) == logging.FileHandler][0]
    logger.info("Script started.")

    # exit if already running
    if not debugtoolkit.DRYRUN and not debugtoolkit.run_once(LOG_FILE):
        logger.warning(f"{NAME_NOEXT} already running, exiting.")
        sys.exit(2)
    sys.excepthook = handle_exception
    atexit.register(exit_process)
    killer = debugtoolkit.KillHandler()
    script_main()


def test01():
    time.sleep(3)
    print('test01')

