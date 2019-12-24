from vfzsync.lib.debugtoolkit import (init_logger, crash_me, debug_exception, deflogger,
                           deflogger_module, dry_request, handle_exception,
                           measure, killer_loop)
from vfzsync.lib.vfzlib import VFZSync
import vfzsync
import time


def run_sync():
    from random import random
    if random() > 0.3:
        logger.debug("random failure")
        time.sleep(2)
        return "failed"

    try:
        vfzsync = VFZSync()
    except Exception:
        logger.exception(f"Failed to initialize vfzsync.")

    else:
        # vPoller -> FNT
        vfzsync.run_vpoller_fnt_sync()

        # FNT -> Zabbix
        vfzsync.run_fnt_zabbix_sync()

    return "done"

logger = init_logger()
