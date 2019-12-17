from debugtoolkit import (
    deflogger,
    dry_request,
    measure,
    init_logger
)
from vpoller.client import VPollerClient
import json


class vPollerAPI:
    @deflogger
    def __init__(self, vpoller_endpoint):
        super().__init__()
        self.client = VPollerClient(endpoint=vpoller_endpoint)

    @measure(operation=sum)
    @deflogger
    def run(self, vc_host, method, name=None, key=None, properties=None):
        msg = {"method": method, "hostname": vc_host}
        for prop in ['name', 'properties', 'key']:
            if eval(prop) is not None:
                msg[prop] = eval(prop)

        response = json.loads(self.client.run(msg))
        if response["success"] == 0:
            result = response["result"]
            return result
        else:
            logger.error(f'Failed to execute method "{method}": {msg}')
            raise vPollerException(f'{response["msg"]}')


class vPollerException(Exception):
    """ vPoller Exception """
    pass


logger = init_logger()
