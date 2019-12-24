import os
import yaml

from flask import Flask


def read_config():
    PATH = os.path.dirname(__file__)
    # PATH_NOEXT = os.path.splitext(__file__)[0]
    NAME_NOEXT = os.path.basename(PATH)
    PATH = os.getcwd()
    config_path = f"{PATH}/config/{NAME_NOEXT}.yaml"
    with open(config_path, mode="r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# globals

CONFIG = read_config()
app = Flask(__name__)
