import requests

from debugtoolkit import (
    deflogger,
    dry_request,
    measure,
    init_logger

)
import sys
import json


class FNTNotAuthorized(Exception):
    pass


class FNTException(Exception):
    pass


class FNTCommandAPI:
    @deflogger
    def __init__(self, url, username, password):
        super().__init__()
        self.fnt_api_url = f"{url}/axis/api/rest"
        self.authorized = False
        self.auth(url, username, password)

    @deflogger
    def send_request(self, method, payload=None, headers=None, params=None, exit=True):
        fnt_api_endpoint = f"{self.fnt_api_url}/{method}"
        if not params and self.authorized:
            params = {"sessionId": self.session_id}

        if not headers:
            headers = {"Content-Type": "application/json", "Accept": "application/json"}
        try:
            response = requests.post(
                url=fnt_api_endpoint, data=json.dumps(payload), headers=headers, params=params, timeout=5,
            )
        except requests.RequestException:
            logger.exception(f"Failed to send request ({fnt_api_endpoint=})")
            if exit:
                sys.exit(3)

        if response:
            if response.json()["status"]["success"]:
                return response.json()
            else:
                logger.error(f'Failed to execute method "{method}": {response.json()["status"]}')
                raise FNTException(f'FNT Exception: {response.json()["status"]}')
        else:
            logger.error(f'Failed to send request for method "{method}": {response}')  # ["status"]}'
            raise FNTException(f"FNT Exception: {response.text}")

    @deflogger
    def auth(self, url, username, password):
        payload = {
            "user": username,
            "password": password,
            "manId": "1001",
            "userGroupName": "Adm|G",
        }
        method = "businessGateway/login"
        response = self.send_request(method=method, payload=payload)
        if response and response["status"]["success"]:
            self.session_id = response["sessionId"]
            self.authorized = True
            return True
        else:
            raise FNTNotAuthorized("Command Unauthorized")

    # def check_auth():
    #     if not self.authorized:
    #         logger.warning(f"Not authorized to execute {method} method")
    #         return False

    @measure(operation=sum)
    @deflogger
    def get_entities(self, entity_type, entity_custom=False, restrictions={}, attributes=[]):
        if entity_custom:
            method = f"entity/custom/{entity_type}/query"
        else:
            method = f"entity/{entity_type}/query"
        payload = {"restrictions": restrictions, "returnAttributes": attributes}

        response = self.send_request(method=method, payload=payload)
        return response["returnData"]

    @measure(operation=sum)
    @deflogger
    def get_related_entities(self, entity_type, entity_elid, relation_type, restrictions={}, attributes=[]):
        method = f"entity/{entity_type}/{entity_elid}/{relation_type}"
        payload = {
            "entityRestrictions": restrictions,
            "returnEntityAttributes": attributes,
        }

        response = self.send_request(method=method, payload=payload)
        response = [entry for entry in response["returnData"]]
        return response

    @deflogger
    def create_entity(self, entity_type, entity_custom=False, **attributes):
        payload = {**attributes}
        if not entity_custom:
            method = f"entity/{entity_type}/create"
        else:
            method = f"entity/custom/{entity_type}/create"

        response = self.send_request(method=method, payload=payload)
        return response["returnData"]

    @deflogger
    def update_entity(self, entity_type, entity_elid, entity_custom=False, **attributes):
        payload = {**attributes}
        if not entity_custom:
            method = f"entity/{entity_type}/{entity_elid}/update"
        else:
            method = f"entity/custom/{entity_type}/{entity_elid}/update"

        response = self.send_request(method=method, payload=payload)
        return response["returnData"]

    @deflogger
    def delete_entity(self, entity_type, entity_elid, entity_custom=False):
        payload = {}
        if not entity_custom:
            method = f"entity/{entity_type}/{entity_elid}/delete"
        else:
            method = f"entity/custom/{entity_type}/{entity_elid}/delete"

        response = self.send_request(method=method, payload=payload)
        return response["returnData"]

    @deflogger
    def create_related_entities(self, entity_type, entity_elid, relation_type, linked_elid):
        attributes = {f"createLink{relation_type}": [{"linkedElid": linked_elid}]}
        response = self.update_entity(entity_type=entity_type, entity_elid=entity_elid, **attributes)
        return response

    # @dryable.Dryable()
    @deflogger
    def delete_related_entities(self, entity_type, entity_elid, relation_type, link_elid):
        attributes = {f"deleteLink{relation_type}": [{"linkElid": link_elid}]}
        response = self.update_entity(entity_type=entity_type, entity_elid=entity_elid, **attributes)
        return response


logger = init_logger()
