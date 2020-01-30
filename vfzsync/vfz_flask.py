from debugtoolkit.debugtoolkit import (init_logger, crash_me, debug_exception, deflogger,
                           deflogger_module, dry_request, handle_exception,
                           measure, killer_loop)
from vfzsync.lib.vfzlib import VFZSync
import vfzsync
import time


def run_sync():
    result = {}

    #dev
    from random import random
    if random() > 0.9:
        logger.debug("random failure")
        time.sleep(1)
        result['message'] = "Random failure."
        result['success'] = False
        return result

    try:
        if random() > 0.9:
            crash_me()
        sync = VFZSync()
        stats = sync.run_sync()

    except Exception as e:
        logger.exception(f"Sync failed.")
        result['message'] = "Sync failed."
        result['exception'] = str(e)
        result['success'] = False
        return result

    result['message'] = "completed"
    result['success'] = True
    result['stats'] = stats
    return result

logger = init_logger()
logger.debug(f'{__name__} init done.')
