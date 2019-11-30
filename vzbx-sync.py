import json
import sys
import logging
import logging.config
import requests
import re
import yaml
import time
import os
import atexit
from urllib3.exceptions import HTTPError as BaseHTTPError
from datetime import datetime
from pprint import pprint  # #dev
from pyzabbix.api import ZabbixAPI, ZabbixAPIException
from vpoller.client import VPollerClient
# import http.client
# http.client.HTTPConnection.debuglevel = 1

sys.path.append(os.path.join(os.path.dirname(__file__), "lib"))
import debug_toolkit
from debug_toolkit import (
    deflogger,
    dry_request,
    measure,
    first,
    handle_exception,
    crash_me,
)

# Read config file
f = open("vzbx-sync_dev.yaml", mode="r", encoding="utf-8")
config = yaml.safe_load(f)

# Flow control
DEBUG = config["general"]["debug"]
DRYRUN = config["general"]["dryrun"]


def exit_process():
    if "db" in globals():
        db.close()
    if "zapi" in globals():
        zapi.user.logout()

    logger.debug("DEBUG summary:")
    if "stats" in globals() and stats:
        logger.debug("[stats]\n", json.dumps(stats, indent=4, sort_keys=False))
    logger.debug("[uptime] {:.2f} s".format(debug_toolkit.get_uptime()))
    logger.debug("[@measure] summary:")
    for dly in debug_toolkit.delays:
        logger.debug("{0}\t {1:.2f} \ts".format(dly, debug_toolkit.delays[dly]))

    logger.info("Stopped.")


sys.excepthook = handle_exception
killer = debug_toolkit.KillHandler()
atexit.register(exit_process)
stats = {}

# Logging
LOG_SUFFIX = ".log"
if DRYRUN:
    LOG_SUFFIX = "_DRYRUN.log"
if DEBUG:
    LOG_SUFFIX = "_DEBUG.log"
if DRYRUN and DEBUG:
    LOG_SUFFIX = "_DRYDEBUG.log"
PATH_NOEXT = os.path.splitext(__file__)[0]
NAME_NOEXT = os.path.splitext(os.path.basename(__file__))[0]
LOG_FILE = PATH_NOEXT + LOG_SUFFIX


config_logging = config["logging"]
config_logging["handlers"]["file"]["filename"] = LOG_FILE
logging.config.dictConfig(config_logging)
logger = logging.getLogger(NAME_NOEXT)
logger.info("Started.")


def flatten(l):
    return [item for sublist in l for item in sublist]


class vPollerAPI:
    def __init__(self, vpoller_endpoint):
        super().__init__()
        self.client = VPollerClient(endpoint=vpoller_endpoint)

    def run(self, vc_host, method, name=None, properties=None):
        msg = {"method": method, "hostname": vc_host}
        if name:
            msg["name"] = name
        if properties:
            msg["properties"] = properties

        response = json.loads(self.client.run(msg))
        if response["success"] == 0:
            result = response["result"]
            return result
        else:
            logger.error(f"Failed to execute {method} method: {msg}")


class FNTNotAuthorized(Exception):
    pass


class FNTCommandAPI:
    def __init__(self, url, username, password):
        super().__init__()
        self.fnt_api_url = "{}/axis/api/rest".format(url)
        self.authorized = False
        self.auth(url, username, password)

    def send_request(self, method, payload=None, headers=None, params=None):
        fnt_api_endpoint = "{}/{}".format(self.fnt_api_url, method)

        if not headers:
            headers = {"Content-Type": "application/json", "Accept": "application/json"}
        try:
            response = requests.post(
                url=fnt_api_endpoint,
                data=json.dumps(payload),
                headers=headers,
                params=params, 
                timeout=5
            )
        except:
            logger.exception(f'Failed to send request ({fnt_api_endpoint=})')
            sys.exit(1)

        if response and response.json()["status"]["success"]:
            return response.json()
        else:
            logger.error(
                f'Failed to execute {method} method: {response.json()["status"]}'
            )

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
    
    def get_entities(
        self, entity_type, entity_custom=False, restrictions={}, attributes=[]
    ):
        if entity_custom:
            method = "entity/custom/{}/query".format(entity_type)
        else:
            method = "entity/{}/query".format(entity_type)
        payload = {"restrictions": restrictions, "returnAttributes": attributes}
        params = {"sessionId": self.session_id}

        response = self.send_request(method=method, payload=payload, params=params)
        return response["returnData"]

    def get_related_entities(
        self, entity_type, entity_elid, relation_type, restrictions={}, attributes=[]
    ):
        method = "entity/{}/{}/{}".format(entity_type, entity_elid, relation_type)
        payload = {
            "entityRestrictions": restrictions,
            "returnEntityAttributes": attributes,
        }
        params = {"sessionId": self.session_id}

        response = self.send_request(method=method, payload=payload, params=params)
        response = [entry["entity"] for entry in response["returnData"]]
        return response

    def create_entity(self, entity_type, entity_custom=False, **attributes):
        payload = {**attributes}
        params = {"sessionId": self.session_id}
        if not entity_custom:
            method = f'entity/{entity_type}/create'
        else:
            method = f'entity/custom/{entity_type}/create'

        response = self.send_request(method=method, payload=payload, params=params)
        return response["returnData"]

    def update_entity(self, entity_type, entity_elid, entity_custom=False, **attributes):
        payload = {**attributes}
        params = {"sessionId": self.session_id}
        if not entity_custom:
            method = f'entity/{entity_type}/{entity_elid}/update'
        else:
            method = f'entity/{entity_type}/{entity_elid}/update'

        response = self.send_request(method=method, payload=payload, params=params)
        return response["returnData"]


@measure(operation=sum)
def get_vpoller_vms(vpoller):
    vpoller_resp = vpoller.run(
        method="vm.discover", vc_host=config["vpoller"]["vc_host"]
    )
    vm_names = [vm["name"] for vm in vpoller_resp]

    vms = []

    for vm_name in vm_names:
        vm = vpoller.run(
            method="vm.get",
            vc_host=config["vpoller"]["vc_host"],
            name=vm_name,
            properties=[
                "name",
                "config.instanceUuid",
                "config.hardware.numCPU",
                "config.hardware.memoryMB",
            ],
        )[0]

        nets = vpoller.run(
            method="vm.guest.net.get",
            vc_host=config["vpoller"]["vc_host"],
            name=vm_name,
            properties=["ipAddress"],
        )

        ips = flatten([net["ipAddress"] for net in nets["net"]])
        ips_v4 = [ip for ip in ips if re.match(r"(\d+\.){3}\d+", ip)]
        vm["ipAddress"] = ips_v4
        vms.append(vm)

    vms_indexed = {vm["config.instanceUuid"]: vm for vm in vms}

    return vms, vms_indexed


@measure(operation=sum)
def get_fnt_virtual_servers(command):
    virtualservers = command.get_entities(
        "virtualServer", attributes=fnt_vs_attributes, restrictions=FNT_VS_FILTER
    )
    virtualservers_indexed = {vs["remark"]: vs for vs in virtualservers}
    for vs in virtualservers:
        vs_ips = command.get_related_entities(
            "virtualServer", entity_elid=vs["elid"], relation_type="CustomVmIpAddresses"
        )
        ips = [vs_ip["ipAddress"] for vs_ip in vs_ips]
        vs["ipAddress"] = ips
    return virtualservers, virtualservers_indexed


@measure(operation=sum)
def get_zabbix_hosts(zapi):
    hosts = zapi.host.get(
        output=["name", "host"],
        selectInterfaces=["ip", "interfaceid", "dns", "type"],
        groupids=zabbix_hostgroup_id,
    )
    hosts_indexed_by_host = {host["host"]: host for host in hosts}
    return hosts, hosts_indexed_by_host


def get_hostgroupid_by_name(zapi, name):
    return int(zapi.hostgroup.get(filter={"name": name})[0]["groupid"])


def get_templateid_by_name(zapi, name):
    return int(zapi.template.get(filter={"host": name})[0]["templateid"])


# def main():

# Initiate vPoller
vpoller = vPollerAPI(vpoller_endpoint=config["vpoller"]["endpoint"])
#vpoller.run(method='about',vc_host=config["vpoller"]["vc_host"])

# Initiate FNT API
try:
    command = FNTCommandAPI(
        url=config["command"]["url"],
        username=config["command"]["username"],
        password=config["command"]["password"],
    )
except FNTNotAuthorized:
    logger.error("FNT Command authorization failed.")
    sys.exit(3)


# Initiate ZabbixAPI
try:
    zapi = ZabbixAPI(
        url=config["zabbix"]["url"],
        user=config["zabbix"]["username"],
        password=config["zabbix"]["password"],
    )
    zapi.session.verify = False
except ZabbixAPIException as e:
    logger.error("Zabbix authorization failed.")
    sys.exit(3)

zabbix_hostgroup_id = get_hostgroupid_by_name(zapi, config["zabbix"]["hostgroup"])
zabbix_template_id = get_templateid_by_name(zapi, config["zabbix"]["template"])


# Main code
LOOP = 1
i = 1 if LOOP != -1 else -1


while i <= LOOP:

    # vPoller -> FNT
    vpoller_vms, vpoller_vms_indexed = get_vpoller_vms(vpoller)

    # FNT

    fnt_vs_attributes = [
        "id",
        "visibleId",
        "elid",
        "cCpu",
        "cRam",
        "cManagementInterface",
        "cCommunityName",
        "cSdiNewServer",
        "cSdiIpChanged",
        "cSdiMonitoring",
        "cSdiDeleted",
        "remark",  # #dev only
    ]

    transform_map_vpoller_fnt = [
        ("config.instanceUuid", "remark"),
        ("name", "visibleId"),
        # ("name", "id"),
        ("config.hardware.numCPU", "cCpu"),
        ("config.hardware.memoryMB", "cRam"),
        #    ("ipAddress", "ipAddress"),
    ]

    transform_map_fnt_zabbix = [
        ("id", "host"),
        ("visibleId", "name"),
        # ("cManagementInterface", zbx_old_hosts[alias]["interfaces"][0]["ip"]),
        ("cCommunityName", "{$SNMP_COMMUNITY}"),
    ]

    FNT_VS_FILTER = {"remark": {"operator": "like", "value": "*-*-*-*-*"}}

    fnt_virtualservers, fnt_virtualservers_indexed = get_fnt_virtual_servers(command)

    vs_update_set = []
    for vm in vpoller_vms:
        vm_uuid = vm["config.instanceUuid"]
        vs_current = fnt_virtualservers_indexed.get(vm_uuid, {})
        vs_attributes = {}
        # compare attributes
        for tm_entry in transform_map_vpoller_fnt:
            vs_attr = tm_entry[1]
            vm_attr = tm_entry[0]
            if vm[vm_attr] != vs_current.get(vs_attr):
                vs_attributes[vs_attr] = vm[vm_attr]
            if vm["ipAddress"] and vm["ipAddress"][0] != vs_current.get("cManagementInterface"):
                vs_attributes["cManagementInterface"] = vm["ipAddress"][0]  # #dev only                
                vs_attributes["cSdiIpChanged"] = 'Y'
        if vs_attributes:
            # vs_update_set.append(vs_attributes)
            try:
                if not vs_current:
                    command.create_entity(entity_type="virtualServer", **vs_attributes, cSdiNewServer="Y")
                    logger.info(f'Created VirtualServer {vs_attributes["visibleId"]}')
                    logger.debug(f'Attributes: {vs_attributes}')
                else:
                    command.update_entity(entity_type="virtualServer", entity_elid=vs_current['elid'], **vs_attributes)
                    logger.info(f'Updated VirtualServer {vs_current["visibleId"]}')
                    logger.debug(f'Attributes: {vs_attributes}')
            except:
                logger.error(f"Failed to create/update VirtualServer: {vs_attributes}")
    
    # for vs_attributes in vs_update_set:
    # mark deleted vss
    for vs in fnt_virtualservers:
        vs_uuid = vs["remark"] # #dev
        if not vpoller_vms_indexed.get(vs_uuid) and vs['cSdiDeleted'] != 'Y':
            try:
                vs_attributes = {"cSdiDeleted": "Y"}
                command.update_entity(entity_type="virtualServer", entity_elid=vs['elid'], **vs_attributes)
                logger.info(f'Updated VirtualServer {vs["visibleId"]}')
                logger.debug(f'Attributes: {vs_attributes}')
            except:
                logger.error(f"Failed to create/update VirtualServer: {vs_attributes}")

    # FNT -> Zabbix
    # Get  hosts
    zabbix_hosts, zabbix_hosts_indexed_by_host = get_zabbix_hosts(zapi)

    fnt_virtualservers, fnt_virtualservers_indexed = get_fnt_virtual_servers(command)

    for vs in fnt_virtualservers:
        try:
            if vs["cManagementInterface"] and not zabbix_hosts_indexed_by_host.get(
                vs["id"]
            ):
                zapi.host.create(
                    host=vs["id"],
                    name=f'{vs["visibleId"]} [{vs["id"]}]',
                    groups=[{"groupid": zabbix_hostgroup_id}],
                    interfaces=[
                        {
                            "type": 2,
                            "main": "1",
                            "useip": 1,
                            "ip": vs["cManagementInterface"],
                            "dns": "",
                            "port": 161,
                        }
                    ],
                    templates=[{"templateid": zabbix_template_id}],
                )
        except Exception as e:
            logger.exception(e)

    if DEBUG:
        logger.debug(f"Loop {i}.")

    sleep_time = 0.01
    for c in range(0, 1000):
        if killer.kill_now:
            logger.info("Stopping..")
            sys.exit(1)
        if LOOP != 1:
            time.sleep(sleep_time)
    if LOOP != -1:
        i += 1

    # debug_toolkit.crash_me()
    # break

# if __name__ == "__main__":
#    main()
