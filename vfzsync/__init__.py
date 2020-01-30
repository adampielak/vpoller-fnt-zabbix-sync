import os
import yaml
import logging
import logging.config

from flask import Flask


def read_config():
    PATH = os.path.dirname(__file__)
    # PATH_NOEXT = os.path.splitext(__file__)[0]
    NAME_NOEXT = os.path.basename(PATH)
    PATH = os.getcwd()
    config_path = f"{PATH}/config/{NAME_NOEXT}.yaml"
    with open(config_path, mode="r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def init_logging():
    # PATH = os.path.dirname(__file__)
    PATH = os.getcwd()
    # PATH_NOEXT = os.path.splitext(__file__)[0]

    LOG_SUFFIX = ".log"
    # if DRYRUN:
    #     LOG_SUFFIX = "_DRYRUN.log"
    # if DEBUG:
    #     LOG_SUFFIX = "_DEBUG.log"
    # if DRYRUN and DEBUG:
    #     LOG_SUFFIX = "_DRYDEBUG.log"
    LOG_FILE = f"{PATH}/log/{NAME_NOEXT}{LOG_SUFFIX}"

    config_logging = CONFIG["logging"]
    config_logging["handlers"]["file"]["filename"] = LOG_FILE
    logging.config.dictConfig(config_logging)
    logger = logging.getLogger(NAME_NOEXT)

    return logger, LOG_FILE


# globals
CONFIG = read_config()

PATH = os.path.dirname(__file__)
# PATH_NOEXT = os.path.splitext(__file__)[0]
NAME_NOEXT = os.path.basename(PATH)

# Logging
logger, LOG_FILE = init_logging()
logger.debug("Started.")

# Flow control
# debugtoolkit should be imported after logging setup
import debugtoolkit.debugtoolkit as debugtoolkit
debugtoolkit.DEBUG = CONFIG["general"]["debug"]
debugtoolkit.TRACE = CONFIG["general"]["trace"]
debugtoolkit.DRYRUN = CONFIG["general"]["dryrun"]
debugtoolkitLOGLEVEL = eval(CONFIG["general"]["loglevel"])
if debugtoolkitLOGLEVEL <= logging.DEBUG:
    debugtoolkit.TRACE = True


app = Flask(__name__)
app.logger.debug(f'{__name__} init done.')
