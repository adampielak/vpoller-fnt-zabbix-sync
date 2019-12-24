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
import vfzsync.lib.debugtoolkit as debugtoolkit
from vfzsync.lib.debugtoolkit import (crash_me, deflogger, measure, handle_exception,
                                       deflogger_module)
from vfzsync.lib.vfzlib import (init_apis, run_fnt_zabbix_sync,
                                 run_vpoller_fnt_sync, test_config, VFZSync)

# import dryable
# import http.client
# http.client.HTTPConnection.debuglevel = 1
# from urllib3.exceptions import HTTPError as BaseHTTPError


@deflogger
def exit_process():
    if TRACE:
        logger.debug("DEBUG summary:")
        if "stats" in globals() and stats:
            logger.debug("[stats]\n", json.dumps(stats, indent=4, sort_keys=False))
        logger.debug(f"[uptime] {debugtoolkit.get_uptime():.2f} s")
        logger.debug("[@measure] summary:")
        for dly in debugtoolkit.delays:
            logger.debug(f"{dly}\t {debugtoolkit.delays[dly]:.2f} \ts")

    logger.info("Stopped.")


@deflogger
def init_logging():
    # PATH = os.path.dirname(__file__)
    PATH = os.getcwd()
    # PATH_NOEXT = os.path.splitext(__file__)[0]

    LOG_SUFFIX = ".log"
    if DRYRUN:
        LOG_SUFFIX = "_DRYRUN.log"
    if DEBUG:
        LOG_SUFFIX = "_DEBUG.log"
    if DRYRUN and DEBUG:
        LOG_SUFFIX = "_DRYDEBUG.log"
    LOG_FILE = f"{PATH}/log/{NAME_NOEXT}{LOG_SUFFIX}"

    config_logging = CONFIG["logging"]
    config_logging["handlers"]["file"]["filename"] = LOG_FILE
    logging.config.dictConfig(config_logging)
    logger = logging.getLogger(NAME_NOEXT)

    if TRACE:
        for module in ['vfzsync', 'vfzsync.lib.fntapi', 'vfzsync.lib.vpollerapi', 'vfzsync.lib.zabbixapi', 'vfzsync.lib.vfzlib']:
            deflogger_module(sys.modules[module], deflogger)
            deflogger_module(sys.modules[module], measure(operation=sum))

    return logger, LOG_FILE


def script_main():
    # test_config()

    # debugtoolkit.crash_me()
    try:
        vfzsync = VFZSync()
    except Exception:
        logger.exception(f"Failed to initialize vfzsync.")
        sys.exit(3)

    for i in debugtoolkit.killer_loop(killer, CONFIG["general"]["loops"], CONFIG["general"]["interval"], exit=True):
        # vPoller -> FNT
        vfzsync.run_vpoller_fnt_sync()

        # FNT -> Zabbix
        vfzsync.run_fnt_zabbix_sync()


# globals

NAME_NOEXT = os.path.splitext(os.path.basename(__file__))[0]

CONFIG = vfzsync.CONFIG

# Flow control
DEBUG = debugtoolkit.DEBUG = CONFIG["general"]["debug"]
TRACE = debugtoolkit.TRACE = CONFIG["general"]["trace"]
DRYRUN = debugtoolkit.DRYRUN = CONFIG["general"]["dryrun"]
# dryable.set(False)


if __name__ == "__main__":
    # Logging
    logger, LOG_FILE = init_logging()
    logger.info("Started.")

    # exit if already running
    if not DRYRUN and not debugtoolkit.run_once(LOG_FILE):
        logger.warning(f"{NAME_NOEXT} already running, exiting.")
        sys.exit(2)
    sys.excepthook = handle_exception
    atexit.register(exit_process)
    killer = debugtoolkit.KillHandler()
    script_main()


def test01():
    time.sleep(3)
    print('test01')

