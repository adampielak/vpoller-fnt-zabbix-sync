#!/usr/bin/env python3
#%%
#sys.path.append(os.path.join(os.path.dirname(__file__), "lib"))
import sys
import os
import json
import logging
import logging.config
import requests
import re
import yaml
import time
import atexit
import math
from datetime import datetime
from pprint import pprint  # #dev
from pyzabbix.api import ZabbixAPI, ZabbixAPIException
from vpoller.client import VPollerClient
import debugtoolkit   # as debugtoolkit
from debugtoolkit import (
    deflogger,
    dry_request,
    measure,
    handle_exception,
    crash_me,
)

# import dryable
# import http.client
# http.client.HTTPConnection.debuglevel = 1
# from urllib3.exceptions import HTTPError as BaseHTTPError


@deflogger
def exit_process():
    # if "zapi" in globals():
    #     zapi.user.logout()
    # if "command" in globals():
    #     pass  # todo

    logger.debug("DEBUG summary:")
    if "stats" in globals() and stats:
        logger.debug("[stats]\n", json.dumps(stats, indent=4, sort_keys=False))
    logger.debug(f"[uptime] {debugtoolkit.get_uptime():.2f} s")
    logger.debug("[@measure] summary:")
    for dly in debugtoolkit.delays:
        logger.debug(f"{dly}\t {debugtoolkit.delays[dly]:.2f} \ts")

    logger.info("Stopped.")


def init_logging():
    LOG_SUFFIX = ".log"
    if DRYRUN:
        LOG_SUFFIX = "_DRYRUN.log"
    if DEBUG:
        LOG_SUFFIX = "_DEBUG.log"
    if DRYRUN and DEBUG:
        LOG_SUFFIX = "_DRYDEBUG.log"
    LOG_FILE = PATH_NOEXT + LOG_SUFFIX

    config_logging = config["logging"]
    config_logging["handlers"]["file"]["filename"] = LOG_FILE
    logging.config.dictConfig(config_logging)
    logger = logging.getLogger(NAME_NOEXT)
    return logger, LOG_FILE


def flatten(l):
    return [item for sublist in l for item in sublist]


def normalize_none(attr):
    if attr is None:
        attr = ''
    return attr


def yes_no(arg, type=bool):
    arg_lower = arg.lower()
    if type == bool:
        if arg_lower == "y" or arg_lower == "yes":
            return True
        return False
    if type == int:
        if arg_lower == "y" or arg_lower == "yes":
            return 1
        return 0


def gib_round(x):
    return round(x / 1024 ** 3, 3)


class vPollerAPI:
    def __init__(self, vpoller_endpoint):
        super().__init__()
        self.client = VPollerClient(endpoint=vpoller_endpoint)

    @deflogger
    def run(self, vc_host, method, name=None, key=None, properties=None):
        msg = {"method": method, "hostname": vc_host}
        if name:
            msg["name"] = name
        if properties:
            msg["properties"] = properties
        if key:
            msg["key"] = key

        response = json.loads(self.client.run(msg))
        if response["success"] == 0:
            result = response["result"]
            return result
        else:
            logger.error(f'Failed to execute method "{method}": {msg}')
        raise vPollerException(f'vPoller Exception: {response["msg"]}')


class vPollerException(Exception):
    pass


class FNTNotAuthorized(Exception):
    pass


class FNTException(Exception):
    pass


class FNTCommandAPI:
    def __init__(self, url, username, password):
        super().__init__()
        self.fnt_api_url = f"{url}/axis/api/rest"
        self.authorized = False
        self.auth(url, username, password)

    @deflogger
    def send_request(self, method, payload=None, headers=None, params=None):
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

    def get_entities(self, entity_type, entity_custom=False, restrictions={}, attributes=[]):
        if entity_custom:
            method = f"entity/custom/{entity_type}/query"
        else:
            method = f"entity/{entity_type}/query"
        payload = {"restrictions": restrictions, "returnAttributes": attributes}

        response = self.send_request(method=method, payload=payload)
        return response["returnData"]

    def get_related_entities(self, entity_type, entity_elid, relation_type, restrictions={}, attributes=[]):
        method = f"entity/{entity_type}/{entity_elid}/{relation_type}"
        payload = {
            "entityRestrictions": restrictions,
            "returnEntityAttributes": attributes,
        }

        response = self.send_request(method=method, payload=payload)
        response = [entry for entry in response["returnData"]]
        return response

    def create_entity(self, entity_type, entity_custom=False, **attributes):
        payload = {**attributes}
        if not entity_custom:
            method = f"entity/{entity_type}/create"
        else:
            method = f"entity/custom/{entity_type}/create"

        response = self.send_request(method=method, payload=payload)
        return response["returnData"]

    def update_entity(self, entity_type, entity_elid, entity_custom=False, **attributes):
        payload = {**attributes}
        if not entity_custom:
            method = f"entity/{entity_type}/{entity_elid}/update"
        else:
            method = f"entity/custom/{entity_type}/{entity_elid}/update"

        response = self.send_request(method=method, payload=payload)
        return response["returnData"]

    def delete_entity(self, entity_type, entity_elid, entity_custom=False):
        payload = {}
        if not entity_custom:
            method = f"entity/{entity_type}/{entity_elid}/delete"
        else:
            method = f"entity/custom/{entity_type}/{entity_elid}/delete"

        response = self.send_request(method=method, payload=payload)
        return response["returnData"]

    def create_related_entities(self, entity_type, entity_elid, relation_type, linked_elid):
        attributes = {f"createLink{relation_type}": [{"linkedElid": linked_elid}]}
        response = self.update_entity(entity_type=entity_type, entity_elid=entity_elid, **attributes)
        return response

    #@dryable.Dryable()
    def delete_related_entities(self, entity_type, entity_elid, relation_type, link_elid):
        attributes = {f"deleteLink{relation_type}": [{"linkElid": link_elid}]}
        response = self.update_entity(entity_type=entity_type, entity_elid=entity_elid, **attributes)
        return response


@measure(operation=sum)
@deflogger
def get_vpoller_vms(vpoller):
    VPOLLER_VM_ATTRIBUTES = [
        "name",
        "config.instanceUuid",
        "config.hardware.numCPU",
        "config.hardware.memoryMB",
        "runtime.powerState",
        "config.annotation"
    ]
    VPOLLER_VM_NET_ATTRIBUTES = ["ipAddress"]
    VPOLLER_VM_DISK_ATTRIBUTES = ["diskPath", "capacity", "freeSpace", "freeSpacePercentage"]
    vpoller_resp = vpoller.run(method="vm.discover", vc_host=config["vpoller"]["vc_host"])
    vm_names = [vm["name"] for vm in vpoller_resp]

    vms = []

    for vm_name in vm_names:
        try:
            vm = vpoller.run(
                method="vm.get",
                vc_host=config["vpoller"]["vc_host"],
                name=vm_name,
                properties=VPOLLER_VM_ATTRIBUTES,
            )[0]

            nets = vpoller.run(
                method="vm.guest.net.get",
                vc_host=config["vpoller"]["vc_host"],
                name=vm_name,
                properties=VPOLLER_VM_NET_ATTRIBUTES,
            )

            disks_discovery = vpoller.run(
                method="vm.disk.discover", vc_host=config["vpoller"]["vc_host"], name=vm_name
            )

            disks_indexed = {}
            for disk_obj in disks_discovery[0]["disk"]:
                disk = vpoller.run(
                    method="vm.disk.get",
                    vc_host=config["vpoller"]["vc_host"],
                    name=vm_name,
                    key=disk_obj["diskPath"],
                    properties=VPOLLER_VM_DISK_ATTRIBUTES,
                )[0]["disk"]
                disks_indexed[disk_obj["diskPath"]] = disk
            # disks_indexed = {disk['diskPath']:disk for disk in disks}
            ips = flatten([net["ipAddress"] for net in nets["net"]])
            ips_v4 = [ip for ip in ips if re.match(r"(\d+\.){3}\d+", ip)]
            ips_indexed = {ip: {"ipAddress": ip} for ip in ips_v4}
            vm["ipAddress"] = ips_indexed
            vm["mountpoint"] = disks_indexed
            vms.append(vm)
        except vPollerException:
            logger.exception(f'Failed to get VM {vm_name} properties.')

    vms_indexed = {vm["config.instanceUuid"]: vm for vm in vms}

    return vms, vms_indexed


#%%
@measure(operation=sum)
@deflogger
def get_fnt_vs(command, index):

    virtualservers = command.get_entities(
        "virtualServer", attributes=FNT_VS_ATTRIBUTES, restrictions=FNT_VS_FILTER
    )
    virtualservers_indexed = {vs[index]: vs for vs in virtualservers}
    for vs in virtualservers:
        for entity_class_name in FNT_VS_LINKED_ENTITIES:
            relation_class_name = FNT_VS_LINKED_ENTITIES[entity_class_name]["relation_class_name_plural"]
            entities = command.get_related_entities(
                "virtualServer", entity_elid=vs["elid"], relation_type=relation_class_name
            )
            index = FNT_VS_LINKED_ENTITIES[entity_class_name]["index"]
            entities_indexed = {entity["entity"][index]: entity for entity in entities}
            vs[entity_class_name] = entities_indexed

        # ips = [vs_ip["ipAddress"] for vs_ip in vs_ips]
        # vs["ipAddress"] = ips
        # vs["ips"] = vs_ips
    return virtualservers, virtualservers_indexed


@measure(operation=sum)
@deflogger
def get_zabbix_hosts(zapi, zabbix_hostgroup_id):
    hosts = zapi.host.get(
        output=["name", "host", "status"],
        selectInterfaces=["ip", "interfaceid", "dns", "type"],
        groupids=zabbix_hostgroup_id,
        selectMacros="extend",
    )
    hosts_indexed_by_host = {host["host"]: host for host in hosts}
    return hosts, hosts_indexed_by_host


@deflogger
def get_zabbix_hostgroupid_by_name(zapi, name):
    groups = zapi.hostgroup.get(filter={"name": name})
    if groups:
        return int(groups[0]["groupid"])
    else:
        return None


@deflogger
def get_zabbix_templateid_by_name(zapi, name):
    return int(zapi.template.get(filter={"host": name})[0]["templateid"])


@deflogger
def sync_fnt_vs(command, vpoller_vms, fnt_virtualservers_indexed):
    # create/update vs
    for vm in vpoller_vms:
        vm_uuid = vm["config.instanceUuid"]
        # do we have a matching vs?
        vs = fnt_virtualservers_indexed.get(vm_uuid, {})
        vs_attr_updateset = {}
        # compare and update attributes
        for tm_entry in VPOLLER_FNT_TRANSFORM_MAP:
            vm_attr, vs_attr = tm_entry
            if vm[vm_attr] != normalize_none(vs.get(vs_attr)):
                vs_attr_updateset[vs_attr] = vm[vm_attr]

        # update linked entities
        if vs:
            sync_fnt_vs_entities(command, vs=vs, vm=vm, vs_attr_updateset=vs_attr_updateset)

        # do we have attributes to create/update
        if vs_attr_updateset:
            create_update_fnt_vs(command, vs=vs, vs_attr_updateset=vs_attr_updateset)


@deflogger
def sync_fnt_vs_entities(command, vs, vm, vs_attr_updateset):
    vs_elid = vs["elid"]
    vs_name = vs["visibleId"]
    hdd_total = hdd_used = 0

    for entity_class_name in FNT_VS_LINKED_ENTITIES:
        vs_entities = vs.get(entity_class_name)
        # entity_class_name = FNT_VS_LINKED_ENTITIES[entity_class_name]["class_name"]
        entity_class_custom = FNT_VS_LINKED_ENTITIES[entity_class_name]["class_custom"]
        entity_relation_class_name = FNT_VS_LINKED_ENTITIES[entity_class_name]["relation_class_name"]
        entity_index = FNT_VS_LINKED_ENTITIES[entity_class_name]["index"]
        entity_transform_map = FNT_VS_LINKED_ENTITIES[entity_class_name]["transform_map"]
        vm_entities = vm.get(entity_index, [])
        # safety: do not sync if no vm data and not marked for deletion
        if not vm_entities and not yes_no(vs_attr_updateset.get('cSdiDeleted', 'N')):
            continue

        # logger.debug(f"{entities=}")
        for entity_key in vm_entities:
            vm_entity = vm[entity_index][entity_key]
            vs_entity = vs_entities.get(entity_key, {}).get('entity', {})
            entity_attr_updateset = {}
            if entity_class_name == "fileSystem":
                vm_entity['capacityGb'] = gib_round(vm_entity["capacity"])
                vm_entity['usedGb'] = gib_round(vm_entity["capacity"] - vm_entity["freeSpace"])
                hdd_total += vm_entity['capacity']
                hdd_used += vm_entity["capacity"] - vm_entity["freeSpace"]
                for tm_entry in entity_transform_map:
                    vm_attr, vs_attr = tm_entry
                    if vm_entity[vm_attr] != normalize_none(vs_entity.get(vs_attr)):
                        entity_attr_updateset[vs_attr] = vm_entity[vm_attr]

            if entity_attr_updateset:
                try:
                    if vs_entity:
                        # logger.debug(f"VirtualServer {vs_name}: Found {entity_class_name}: {vs_entity}")
                        command.update_entity(entity_type=entity_class_name, entity_elid=vs_entity["elid"], **entity_attr_updateset)
                        logger.info(f"VirtualServer {vs_name}: Updated {entity_class_name}: {entity_attr_updateset}.")
                    # new entity
                    else:
                        new_entity = command.create_entity(
                            entity_type=entity_class_name, entity_custom=entity_class_custom, **entity_attr_updateset
                        )
                        new_entity_elid = new_entity["elid"]
                        new_entity_link = command.create_related_entities(
                            entity_type="virtualServer",
                            entity_elid=vs_elid,
                            relation_type=entity_relation_class_name,
                            linked_elid=new_entity_elid,
                        )
                        logger.info(f"VirtualServer {vs_name}: Created {entity_class_name}: {entity_attr_updateset}.")

                except FNTException:
                    logger.exception(
                        f"VirtualServer {vs_name}: Failed to create/update {entity_class_name}: {entity_attr_updateset}."
                    )

    hdd_used, hdd_total = list(map(gib_round, [hdd_used, hdd_total]))
    transform_map = [
        (hdd_used, 'cSdiHddUsed'),
        (hdd_total, 'cSdHddTotal')
    ]
    for tm_entry in transform_map:
        vm_attr, vs_attr = tm_entry
        if vs[vs_attr] != vm_attr:
            vs_attr_updateset[vs_attr] = vm_attr

    cleanup_fnt_vs_entities(
        command, vs, vm, vs_entities, entity_class_name, vs_attr_updateset, entity_index, entity_class_custom,
    )


@deflogger
def create_update_fnt_vs_entities(command, entity_attr_updateset, vs_entity=None, entity_class_name=None, entity_class_custom=False):
    try:
        if not vs_entity:
            command.create_entity(entity_type="virtualServer", **entity_attr_updateset)
            logger.info(f'Created VirtualServer {entity_attr_updateset["visibleId"]}.')
        else:
            command.update_entity(entity_type="virtualServer", entity_elid=vs_entity["elid"], **entity_attr_updateset)
            logger.info(f'Updated VirtualServer {vs_entity["visibleId"]}.')
        logger.debug(f"VirtualServer attributes: {entity_attr_updateset}")
    except FNTException:
        logger.error(f"Failed to create/update VirtualServer: {entity_attr_updateset}.")


@deflogger
def cleanup_fnt_vs_entities(
    command, vs, vm, vs_entities, entity_class_name, vs_attr_updateset, entity_index, entity_class_custom,
    delete_if_empty=False
):

    for entity in vs_entities:
        linked_entity = vs_entities[entity]["entity"][entity_index]
        vm_entities = vm.get(entity_index, [])
        #if not delete_if_empty and not vm_entities:
        if not vm_entities and not yes_no(vs_attr_updateset.get('cSdiDeleted', 'N')):
            return
        if linked_entity not in vm_entities:
            # link_elid = entities[entity]["relation"]["linkElid"]
            linked_elid = vs_entities[entity]["entity"]["elid"]
            if entity_class_name == "vmIpAddress":
                if vs["cManagementInterface"] == linked_entity:
                    vs_attr_updateset["cManagementInterface"] = ""
                    vs_attr_updateset["cSdiMonitoring"] = "N"
            command.delete_entity(
                entity_type=entity_class_name, entity_custom=entity_class_custom, entity_elid=linked_elid,
            )
            # command.delete_related_entities(
            #     "virtualServer", vs_elid, entity_relation_class_name, link_elid
            # )
            logger.info(
                f"VirtualServer {vs['visibleId']}: Deleted entity {entity_class_name}: {linked_entity}"
            )


@deflogger
def create_update_fnt_vs(command, vs_attr_updateset, vs=None):
    try:
        if not vs:
            vs_attr_updateset["cSdiNewServer"] = 'Y'
            #vs_attr_updateset["cSdiStatus"] = 'PowerOn'
            vs_attr_updateset["cSdiLastBackup"] = "2011-11-11T12:00:00Z"
            command.create_entity(entity_type="virtualServer", **vs_attr_updateset)
            logger.info(f'Created VirtualServer {vs_attr_updateset["visibleId"]}.')
        else:
            command.update_entity(entity_type="virtualServer", entity_elid=vs["elid"], **vs_attr_updateset)
            logger.info(f'Updated VirtualServer {vs["visibleId"]}.')
        logger.debug(f"VirtualServer attributes: {vs_attr_updateset}")
    except FNTException:
        logger.error(f"Failed to create/update VirtualServer: {vs_attr_updateset}.")


@deflogger
def cleanup_fnt_vs(command, fnt_virtualservers, vpoller_vms_indexed):
    for vs in fnt_virtualservers:
        vs_uuid = vs["cUuid"]  # #dev
        vs_attr_updateset = {}
        if not vpoller_vms_indexed.get(vs_uuid) and not yes_no(vs["cSdiDeleted"]):
            vs_attr_updateset = {"cSdiDeleted": "Y", "cSdiMonitoring": "N"}
            try:
                sync_fnt_vs_entities(vs=vs, vm={}, vs_attr_updateset=vs_attr_updateset)
                command.update_entity(
                    entity_type="virtualServer", entity_elid=vs["elid"], **vs_attr_updateset
                )
                # cleanup_fnt_vs_entities(
                #     vs, vm={}, entities, entity_class_name, vs_attr_updateset, entity_index, entity_class_custom,
                # )


            except FNTException:
                logger.error(f"Failed to create/update VirtualServer: {vs_attr_updateset}.")
            else:
                logger.debug(f"Update set: {vs_attr_updateset}")
                logger.info(f'Updated VirtualServer {vs["visibleId"]}.')


@measure(operation=sum)
@deflogger
def run_vpoller_fnt_sync(vpoller, command):

    vpoller_vms, vpoller_vms_indexed = get_vpoller_vms(vpoller)
    fnt_virtualservers, fnt_virtualservers_indexed = get_fnt_vs(command=command, index="cUuid")

    sync_fnt_vs(command, vpoller_vms, fnt_virtualservers_indexed)

    cleanup_fnt_vs(command, fnt_virtualservers, vpoller_vms_indexed)


def sync_zabbix_hosts(zapi, fnt_virtualservers, zabbix_hosts_indexed_by_host):
    zabbix_hostgroup_id = get_zabbix_hostgroupid_by_name(zapi, config["zabbix"]["hostgroup"])
    zabbix_template_id = get_zabbix_templateid_by_name(zapi, config["zabbix"]["template"])

    for vs in fnt_virtualservers:
        host = zabbix_hosts_indexed_by_host.get(vs["id"], {})
        host_updateset = {}
        hostinterface_updateset = {}
        if not host:
            # create host
            if yes_no(vs["cSdiMonitoring"]) and vs["cManagementInterface"] and not yes_no(vs["cSdiDeleted"]):
                # name = f'{vs["visibleId"]} [{vs["id"]}]',
                host_updateset = {
                    "host": vs["id"],
                    "name": vs["visibleId"],
                    "groups": [{"groupid": zabbix_hostgroup_id}],
                    "interfaces": [
                        {
                            "type": 2,
                            "main": "1",
                            "useip": 1,
                            "ip": vs["cManagementInterface"],
                            "dns": "",
                            "port": 161,
                        }
                    ],
                    "macros": [
                        {"macro": "{$SNMP_COMMUNITY}", "value": vs["cCommunityName"]},
                        {"macro": "{$VSPHERE.HOST}", "value": config["vpoller"]["vc_host"]}
                        ],
                    "templates": [{"templateid": zabbix_template_id}],
                }

                try:
                    zapi.host.create(**host_updateset)
                except Exception:
                    logger.exception(f'Failed to create Zabbix host {vs["visibleId"]}.')
                else:
                    logger.info(f'Created Zabbix host {vs["visibleId"]}.')
        else:
            # update/delete host
            host_id = host["hostid"]
            if host["macros"]:
                host_macro = [macro for macro in host["macros"] if macro["macro"] == "{$SNMP_COMMUNITY}"][0]
                host_community = host_macro["value"]
            else:
                host_community = ""
            host_interface = host["interfaces"][0]
            host_interface_id = host_interface["interfaceid"]
            host_ip = host_interface["ip"]
            host_name = host["name"]
            if vs["cManagementInterface"] and host_ip != vs["cManagementInterface"]:
                hostinterface_updateset = {"interfaceid": host_interface_id, "ip": vs["cManagementInterface"]}

            if host_name != vs["visibleId"]:
                host_updateset["name"] = vs["visibleId"]

            if vs["cCommunityName"] and host_community != vs["cCommunityName"]:
                host_updateset["macros"] = [{"macro": "{$SNMP_COMMUNITY}", "value": vs["cCommunityName"]}]

            if (host_status := int(not yes_no(vs["cSdiMonitoring"]))) != int(host["status"]):  # noqa
                host_updateset["hostid"] = host_id
                host_updateset["status"] = host_status

            if hostinterface_updateset:
                try:
                    zapi.hostinterface.update(**hostinterface_updateset)
                except Exception:
                    logger.exception(f'Failed to update Zabbix host {vs["visibleId"]} interface.')
                else:
                    logger.debug(f"Update set: {hostinterface_updateset}")
                    logger.info(f'Updated Zabbix host interface {vs["visibleId"]}.')

            if host_updateset:
                host_updateset["hostid"] = host_id
                try:
                    zapi.host.update(**host_updateset)
                except Exception:
                    logger.exception(f'Failed to update Zabbix host {vs["visibleId"]}.')
                else:
                    logger.debug(f"Update set: {host_updateset}")
                    logger.info(f'Updated Zabbix host {vs["visibleId"]}.')


def cleanup_zabbix_hosts(zapi, zabbix_hosts, fnt_virtualservers_indexed):
    for host in zabbix_hosts:
        host_id = host["hostid"]
        # host["host"] not in fnt_virtualservers_indexed
        if fnt_virtualservers_indexed and yes_no(
            fnt_virtualservers_indexed.get(host["host"], {}).get("cSdiDeleted", "N")
        ):
            try:
                zapi.host.delete(host_id)
            except Exception:
                logger.exception(f'Failed to delete Zabbix host {host["host"]}.')
            else:
                logger.info(f'Deleted Zabbix host {host["host"]}.')


@measure(operation=sum)
@deflogger
def run_fnt_zabbix_sync(command, zapi):

    FNT_ZABBIX_TRANSFORM_MAP = [
        ("id", "host"),
        ("visibleId", "name"),
        ("cCommunityName", "{$SNMP_COMMUNITY}"),
    ]

    fnt_virtualservers, fnt_virtualservers_indexed = get_fnt_vs(command=command, index="id")
    zabbix_hostgroup_id = get_zabbix_hostgroupid_by_name(zapi, config["zabbix"]["hostgroup"])
    zabbix_hosts, zabbix_hosts_indexed_by_host = get_zabbix_hosts(zapi, zabbix_hostgroup_id)

    sync_zabbix_hosts(
        zapi, fnt_virtualservers=fnt_virtualservers, zabbix_hosts_indexed_by_host=zabbix_hosts_indexed_by_host
    )

    # cleanup
    cleanup_zabbix_hosts(zapi, zabbix_hosts=zabbix_hosts, fnt_virtualservers_indexed=fnt_virtualservers_indexed)


#%%
# Read config file
PATH_NOEXT = os.path.splitext(__file__)[0]
NAME_NOEXT = os.path.splitext(os.path.basename(__file__))[0]
# CONFIG_PATH = f"{PATH_NOEXT}_dev.yaml"
CONFIG_PATH = f"{PATH_NOEXT}.yaml"
f = open(CONFIG_PATH, mode="r", encoding="utf-8")
config = yaml.safe_load(f)
LOOPS = config["general"]["loops"]
INTERVAL = config["general"]["interval"]

# Flow control
DEBUG = debugtoolkit.DEBUG = config["general"]["debug"]
TRACE = debugtoolkit.TRACE = config["general"]["trace"]
DRYRUN = debugtoolkit.DRYRUN = config["general"]["dryrun"]
# dryable.set(False)

sys.excepthook = handle_exception
killer = debugtoolkit.KillHandler()
atexit.register(exit_process)
stats = {}

# Logging
logger, LOG_FILE = init_logging()

# exit if already running
if not DRYRUN and not debugtoolkit.run_once(LOG_FILE):
    logger.warning(f"{NAME_NOEXT} already running, exiting.")
    sys.exit(2)
FNT_VS_ATTRIBUTES = [
    "id",
    "visibleId",
    "elid",
    "cCpu",
    "cRam",
    "cManagementInterface",
    "cCommunityName",
    "cSdiNewServer",
    "cSdiMonitoring",
    "cSdiDeleted",
    "cUuid",
    "cSdiStatus",
    "cSdHddTotal",
    "cSdiHddUsed",
    "cSdiBackupNeeded",     #todo
    "cSdiLastBackup",       #todo
    "cSdiMonitoringSnmp",   #todo
    "cSdiNoShutdown",       #todo
    "remark"
]

VPOLLER_FNT_TRANSFORM_MAP = [
    ("config.instanceUuid", "cUuid"),
    ("name", "visibleId"),
    ("config.hardware.numCPU", "cCpu"),
    ("config.hardware.memoryMB", "cRam"),
    ("runtime.powerState", "cSdiStatus"),
    ("config.annotation", "remark")
]

FNT_VS_LINKED_IP_TRANSFORM_MAP = [("ipAddress", "ipAddress")]
FNT_VS_LINKED_FS_TRANSFORM_MAP = [
    ("diskPath", "mountpoint"),
    # ("capacity", "capacityGb"),
    ('capacityGb', 'capacityGb'),
    ('usedGb', 'usedGb')
]
FNT_VS_LINKED_ENTITIES = {
    "vmIpAddress": {
        "index": "ipAddress",
        "class_name": "vmIpAddress",
        "class_custom": True,
        "relation_class_name": "CustomVmIpAddress",
        "relation_class_name_plural": "CustomVmIpAddresses",
        "transform_map": FNT_VS_LINKED_IP_TRANSFORM_MAP,
    },
    "fileSystem": {
        "index": "mountpoint",
        "class_name": "fileSystem",
        "class_custom": False,
        "relation_class_name": "FileSystem",
        "relation_class_name_plural": "FileSystems",
        "transform_map": FNT_VS_LINKED_FS_TRANSFORM_MAP,
    },
}

FNT_VS_FILTER = {"cUuid": {"operator": "like", "value": "*-*-*-*-*"}}

logger.info("Started.")


#%%
# Main code
def init_apis():
    #global vpoller, command, zapi

    # Initiate vPoller
    try:
        vpoller = vPollerAPI(vpoller_endpoint=config["vpoller"]["endpoint"])
        vpoller.run(method="about", vc_host=config["vpoller"]["vc_host"])
    except vPollerException:
        logger.exception("vPoller exception")
        sys.exit(3)

    # Initiate FNT API
    try:
        command = FNTCommandAPI(
            url=config["command"]["url"],
            username=config["command"]["username"],
            password=config["command"]["password"],
        )
    except FNTNotAuthorized:
        logger.exception("FNT Command authorization failed.")
        sys.exit(3)

    # Initiate ZabbixAPI
    try:
        zapi = ZabbixAPI(
            url=config["zabbix"]["url"],
            user=config["zabbix"]["username"],
            password=config["zabbix"]["password"],
        )
        zapi.session.verify = False
        zabbix_hostgroup_name = config["zabbix"]["hostgroup"]
        zabbix_hostgroup_id = get_zabbix_hostgroupid_by_name(zapi, zabbix_hostgroup_name)
        if not zabbix_hostgroup_id:
            zabbix_hostgroup_id = zapi.hostgroup.create(name=zabbix_hostgroup_name)
            logger.info(f"Created Zabbix host group {zabbix_hostgroup_name}.")

    except ZabbixAPIException:
        logger.exception("Zabbix authorization failed.")
        sys.exit(3)

    return vpoller, command, zapi


def main():

    vpoller, command, zapi = init_apis()

    i = 0
    while ((i := i + 1) and i <= LOOPS) or LOOPS == -1:  # noqa
        loop_start_time = datetime.now()
        logger.debug(f"Loop {i}.")
#%%
        # vPoller -> FNT
        run_vpoller_fnt_sync(vpoller, command)
#%%
        # FNT -> Zabbix
        run_fnt_zabbix_sync(command, zapi)
#%%
        if LOOPS != 1:
            debugtoolkit.killer_sleep(start_time=loop_start_time, period=INTERVAL, killer=killer)

        # debugtoolkit.crash_me()
        # break


if __name__ == "__main__":
    main()
