import datetime
import json
import math
import os
import re
import sys
import time

from dateutil import parser
from pyzabbix.api import ZabbixAPI, ZabbixAPIException

import vfzsync

import debugtoolkit.debugtoolkit as debugtoolkit
from debugtoolkit.debugtoolkit import (init_logger, crash_me, debug_exception, deflogger,
                           deflogger_module, dry_request, handle_exception,
                           measure)
from .extrafuncs import *
from .fntapi import *
from .vpollerapi import *
from .zabbixapi import *


# globals

VPOLLER_FNT_TRANSFORM_MAP = [
    ("config.instanceUuid", "cUuid"),
    ("name", "visibleId"),
    ("config.hardware.numCPU", "cCpu"),
    ("config.hardware.memoryMB", "cRam"),
    ("runtime.powerState", "cSdiStatus"),
    ("config.annotation", "remark"),
    ("last_backup", "cSdiLastBackup"),
    ("vc_host", "datasource"),
]

FNT_VS_LINKED_IP_TRANSFORM_MAP = [("ipAddress", "ipAddress")]
FNT_VS_LINKED_FS_TRANSFORM_MAP = [
    ("diskPath", "mountpoint"),
    # ("capacity", "capacityGb"),
    ("capacityGb", "capacityGb"),
    ("usedGb", "usedGb"),
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

VPOLLER_VM_ATTRIBUTES = [
    "name",
    "config.instanceUuid",
    "config.hardware.numCPU",
    "config.hardware.memoryMB",
    "runtime.powerState",
    "config.annotation",
]
VPOLLER_VM_NET_ATTRIBUTES = ["ipAddress"]
VPOLLER_VM_DISK_ATTRIBUTES = ["diskPath", "capacity", "freeSpace", "freeSpacePercentage"]

FNT_VS_FILTER = {
    # "cUuid": {"operator": "like", "value": "*-*-*-*-*"},
    "datasource": {"operator": "=", "value": vfzsync.CONFIG["vpoller"]["vc_host"]},
}

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
    "cCSdiDelConfirmed",
    "cUuid",
    "cSdiStatus",
    "cSdHddTotal",
    "cSdiHddUsed",
    "cSdiBackupNeeded",
    "cSdiLastBackup",
    "cSdiMonitoringSnmp",
    "cSdiNoShutdown",
    "remark",
    "datasource"
]

def init_tracing():
    if debugtoolkit.TRACE:
        for module in ['vfzsync', 'vfzsync.lib.fntapi', 'vfzsync.lib.vpollerapi', 'vfzsync.lib.zabbixapi', 'vfzsync.lib.vfzlib']:
            if module in sys.modules:
                deflogger_module(sys.modules[module], deflogger, deflogger_class)
                deflogger_module(sys.modules[module], measure(operation=sum))


def test_config():
    # print(vfzsync.CONFIG)
    print('test_config')


def gib_round(x):
    return round(x / 1024 ** 3, 3)


def datetime_to_local_timezone(dt):
    epoch = dt.timestamp() # Get POSIX timestamp of the specified datetime.
    st_time = time.localtime(epoch) #  Get struct_time for the timestamp. This will be created using the system's locale and it's time zone information.
    tz = datetime.timezone(datetime.timedelta(seconds = st_time.tm_gmtoff)) # Create a timezone object with the computed offset in the struct_time.
    return dt.astimezone(tz) # Move the datetime instance to the new time zone.


def get_vpoller_vms(vpoller):
    vpoller_resp = vpoller.run(method="vm.discover", vc_host=vfzsync.CONFIG["vpoller"]["vc_host"])
    vm_names = [vm["name"] for vm in vpoller_resp]

    vms = []

    for vm_name in vm_names:
        try:
            vm = vpoller.run(
                method="vm.get",
                vc_host=vfzsync.CONFIG["vpoller"]["vc_host"],
                name=vm_name,
                properties=VPOLLER_VM_ATTRIBUTES,
            )[0]

            nets = vpoller.run(
                method="vm.guest.net.get",
                vc_host=vfzsync.CONFIG["vpoller"]["vc_host"],
                name=vm_name,
                properties=VPOLLER_VM_NET_ATTRIBUTES,
            )

            disks_discovery = vpoller.run(
                method="vm.disk.discover", vc_host=vfzsync.CONFIG["vpoller"]["vc_host"], name=vm_name
            )

            disks_indexed = {}
            for disk_obj in disks_discovery[0]["disk"]:
                disk = vpoller.run(
                    method="vm.disk.get",
                    vc_host=vfzsync.CONFIG["vpoller"]["vc_host"],
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
            logger.exception(f"Failed to get VM {vm_name} properties.")

    vms_indexed = {vm["config.instanceUuid"]: vm for vm in vms}

    return vms, vms_indexed


#%%
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


def sync_fnt_vs(command, vpoller_vms, fnt_virtualservers_indexed):

    # create/update vs
    for vm in vpoller_vms:
        vm_uuid = vm["config.instanceUuid"]
        vm_annotation = vm["config.annotation"]

        # do we have a matching vs?
        vs = fnt_virtualservers_indexed.get(vm_uuid, {})
        vs_attr_updateset = {}

        # populate extra vm attributes
        # vm["last_backup"] = "1970-01-01T00:00:00Z"  # default backup date
        vm["last_backup"] = None
        vm["vc_host"] = vfzsync.CONFIG["vpoller"]["vc_host"]
        # vm['last_backup'] = None
        if m := re.match(r".*Time: \[(\d\d\.\d\d\.\d\d\d\d .*?)\].*", vm_annotation):    # noqa
            last_backup = m.group(1)
            last_backup = re.sub(
                r"(\d{2})\.(\d{2})\.(\d{4}) (\d{2}:\d{2}:\d{2})", f'\\3-\\2-\\1T\\4{(time.strftime("%z", time.localtime()))}', last_backup
            )
            vm["last_backup"] = last_backup
            if vs.get('cSdiLastBackup'):
                last_backup_local = datetime_to_local_timezone(parser.parse(vs['cSdiLastBackup'])).strftime("%Y-%m-%dT%H:%M:%S%z")
                vs['cSdiLastBackup'] = last_backup_local

        # compare and update attributes
        # VPOLLER_FNT_TRANSFORM_MAP.append(())
        for tm_entry in VPOLLER_FNT_TRANSFORM_MAP:
            vm_attr, vs_attr = tm_entry
            if normalize_none(vm.get(vm_attr, "")) != normalize_none(vs.get(vs_attr)):
                vs_attr_updateset[vs_attr] = vm[vm_attr]

        # update linked entities
        if vs:
            sync_fnt_vs_entities(command, vs=vs, vm=vm, vs_attr_updateset=vs_attr_updateset)
            # undelete vs if dsiScovered again
            if yes_no(vs['cSdiDeleted']): 
                vs_attr_updateset['cSdiDeleted'] = 'N'
                vs_attr_updateset['cSdiNewServer'] = 'Y'

        # do we have attributes to create/update
        if vs_attr_updateset:
            create_update_fnt_vs(command, vs=vs, vs_attr_updateset=vs_attr_updateset)


def sync_fnt_vs_entities(command, vs, vm, vs_attr_updateset):
    vs_elid = vs["elid"]
    vs_name = vs["visibleId"]
    hdd_total = hdd_used = 0

    for entity_class_name in FNT_VS_LINKED_ENTITIES:
        vs_entities = vs.get(entity_class_name)
        # entity_class_name = FNT_VS_LINKED_ENTITIES[entity_class_name]["class_name"]
        entity_definition = FNT_VS_LINKED_ENTITIES[entity_class_name]
        entity_class_custom = entity_definition["class_custom"]
        entity_relation_class_name = entity_definition["relation_class_name"]
        entity_index = entity_definition["index"]
        entity_transform_map = entity_definition["transform_map"]
        vm_entities = vm.get(entity_index, [])
        # safety: do not sync if no vm data and not marked for deletion
        # if not vm_entities and not yes_no(vs_attr_updateset.get("cSdiDeleted", "N")):
        #     continue

        # logger.debug(f"{entities=}")
        for entity_key in vm_entities:
            vm_entity = vm[entity_index][entity_key]
            vs_entity = vs_entities.get(entity_key, {}).get("entity", {})
            entity_attr_updateset = {}
            if entity_class_name == "fileSystem":
                vm_entity["capacityGb"] = gib_round(vm_entity["capacity"])
                vm_entity["usedGb"] = gib_round(vm_entity["capacity"] - vm_entity["freeSpace"])
                hdd_total += vm_entity["capacity"]
                hdd_used += vm_entity["capacity"] - vm_entity["freeSpace"]
            for tm_entry in entity_transform_map:
                vm_attr, vs_attr = tm_entry
                if vm_entity[vm_attr] != normalize_none(vs_entity.get(vs_attr)):
                    entity_attr_updateset[vs_attr] = vm_entity[vm_attr]

            if entity_attr_updateset:
                try:
                    if vs_entity:
                        # logger.debug(f"VirtualServer {vs_name}: Found {entity_class_name}: {vs_entity}")
                        command.update_entity(
                            entity_type=entity_class_name,
                            entity_elid=vs_entity["elid"],
                            **entity_attr_updateset,
                        )
                        logger.info(
                            f"VirtualServer {vs_name}: Updated {entity_class_name}: {entity_attr_updateset}."
                        )
                    # new entity
                    else:
                        new_entity = command.create_entity(
                            entity_type=entity_class_name,
                            entity_custom=entity_class_custom,
                            **entity_attr_updateset,
                        )
                        new_entity_elid = new_entity["elid"]
                        new_entity_link = command.create_related_entities(
                            entity_type="virtualServer",
                            entity_elid=vs_elid,
                            relation_type=entity_relation_class_name,
                            linked_elid=new_entity_elid,
                        )
                        logger.info(
                            f"VirtualServer {vs_name}: Created {entity_class_name}: {entity_attr_updateset}."
                        )

                except FNTException:
                    logger.exception(
                        f"VirtualServer {vs_name}: Failed to create/update {entity_class_name}: {entity_attr_updateset}."
                    )

        cleanup_fnt_vs_entities(
            command,
            vs,
            vm,
            vs_entities,
            entity_class_name,
            vs_attr_updateset,
            entity_index,
            entity_class_custom,
        )

    # update aggregated attrs
    hdd_used, hdd_total = list(map(gib_round, [hdd_used, hdd_total]))
    transform_map = [(hdd_used, "cSdiHddUsed"), (hdd_total, "cSdHddTotal")]
    for tm_entry in transform_map:
        vm_attr, vs_attr = tm_entry
        if vs[vs_attr] != vm_attr:
            vs_attr_updateset[vs_attr] = vm_attr


#region
# todo
# def create_update_fnt_vs_entities(command, entity_attr_updateset, vs_entity=None,
# entity_class_name=None, entity_class_custom=False):
#     try:
#         if not vs_entity:
#             command.create_entity(entity_type="virtualServer", **entity_attr_updateset)
#             logger.info(f'Created VirtualServer {entity_attr_updateset["visibleId"]}.')
#         else:
#             command.update_entity(entity_type="virtualServer", entity_elid=vs_entity["elid"], **entity_attr_updateset)
#             logger.info(f'Updated VirtualServer {vs_entity["visibleId"]}.')
#         logger.debug(f"VirtualServer attributes: {entity_attr_updateset}")
#     except FNTException:
#         logger.error(f"Failed to create/update VirtualServer: {entity_attr_updateset}.")
#endregion


def cleanup_fnt_vs_entities(
    command,
    vs,
    vm,
    vs_entities,
    entity_class_name,
    vs_attr_updateset,
    entity_index,
    entity_class_custom,
    delete_if_empty=False,
):

    for entity in vs_entities:
        linked_entity = vs_entities[entity]["entity"][entity_index]
        vm_entities = vm.get(entity_index, [])
        # if not delete_if_empty and not vm_entities:
        if not vm_entities and not yes_no(vs_attr_updateset.get("cSdiDeleted", "N")):
            return
        if linked_entity not in vm_entities:
            # link_elid = entities[entity]["relation"]["linkElid"]
            linked_elid = vs_entities[entity]["entity"]["elid"]
            if entity_class_name == "vmIpAddress":
                if vs["cManagementInterface"] == linked_entity:
                    vs_attr_updateset["cManagementInterface"] = ""
                    vs_attr_updateset["cSdiMonitoring"] = "N"
                    vs_attr_updateset["cSdiMonitoringSnmp"] = "N"
            command.delete_entity(
                entity_type=entity_class_name, entity_custom=entity_class_custom, entity_elid=linked_elid,
            )
            # command.delete_related_entities(
            #     "virtualServer", vs_elid, entity_relation_class_name, link_elid
            # )
            logger.info(
                f"VirtualServer {vs['visibleId']}: Deleted entity {entity_class_name}: {linked_entity}"
            )


def create_update_fnt_vs(command, vs_attr_updateset, vs=None):
    try:
        if not vs:
            vs_attr_updateset["cSdiNewServer"] = "Y"
            command.create_entity(entity_type="virtualServer", **vs_attr_updateset)
            logger.info(f'Created VirtualServer {vs_attr_updateset["visibleId"]}.')
        else:
            command.update_entity(entity_type="virtualServer", entity_elid=vs["elid"], **vs_attr_updateset)
            logger.info(f'Updated VirtualServer {vs["visibleId"]}.')
        logger.debug(f"VirtualServer attributes: {vs_attr_updateset}")
    except FNTException:
        logger.error(f"Failed to create/update VirtualServer: {vs_attr_updateset}.")


def cleanup_fnt_vs(command, fnt_virtualservers, vpoller_vms_indexed):
    for vs in fnt_virtualservers:
        vs_uuid = vs["cUuid"]  # #dev
        vs_attr_updateset = {}
        if not vpoller_vms_indexed.get(vs_uuid) and not yes_no(vs["cSdiDeleted"]):
            vs_attr_updateset = {"cSdiDeleted": "Y", "cSdiMonitoring": "N", "cSdiMonitoringSnmp": "N"}
            try:
                sync_fnt_vs_entities(command, vs=vs, vm={}, vs_attr_updateset=vs_attr_updateset)
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


def sync_zabbix_hosts(zapi, fnt_virtualservers, zabbix_hosts_indexed_by_host):
    zabbix_hostgroup_id = get_zabbix_hostgroupid_by_name(zapi, vfzsync.CONFIG["zabbix"]["hostgroup"])
    zabbix_template_id = get_zabbix_templateid_by_name(zapi, vfzsync.CONFIG["zabbix"]["template"])
    zabbix_proxy_id = get_zabbix_proxyid_by_name(zapi, vfzsync.CONFIG["zabbix"]["proxy"])

    for vs in fnt_virtualservers:
        host = zabbix_hosts_indexed_by_host.get(vs["id"], {})
        host_updateset = {}
        hostinterface_updateset = {}
        if not host:
            # create host
            if vs["cManagementInterface"] and not yes_no(vs["cSdiDeleted"]):
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
                        {"macro": "{$VSPHERE.HOST}", "value": vfzsync.CONFIG["vpoller"]["vc_host"]},
                    ],
                    "templates": [{"templateid": zabbix_template_id}],
                    "proxy_hostid": str(zabbix_proxy_id)
                }

                try:
                    zapi.host.create(**host_updateset)
                except ZabbixAPIException:
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
            host_triggers, host_triggers_by_tag = get_zabbix_host_triggers(zapi=zapi, hostids=host_id)

            # FNT_ZABBIX_TRANSFORM_MAP = [
            #     ("cManagementInterface", host_ip),
            #     ("visibleId", "name"),
            #     ("cCommunityName", host_community)
            # ]

            if host_name != vs["visibleId"]:
                host_updateset["name"] = vs["visibleId"]

            if vs["cManagementInterface"] and host_ip != vs["cManagementInterface"]:
                hostinterface_updateset = {"interfaceid": host_interface_id, "ip": vs["cManagementInterface"]}

            if vs["cCommunityName"] and host_community != vs["cCommunityName"]:
                host_updateset["macros"] = [
                    {"macro": "{$SNMP_COMMUNITY}", "value": vs["cCommunityName"]},
                    {"macro": "{$VSPHERE.HOST}", "value": vfzsync.CONFIG["vpoller"]["vc_host"]}
                ]

            host_status = '1'
            hosttriggers_updateset = []
            FNT_ZABBIX_FLAG_TRIGGERS = ["cSdiMonitoring", "cSdiMonitoringSnmp", "cSdiNoShutdown", "cSdiBackupNeeded"]
            for vs_flag in FNT_ZABBIX_FLAG_TRIGGERS:
                if yes_no(vs[vs_flag]):
                    host_status = '0'
                trigger = host_triggers_by_tag[vs_flag]
                vs_flag_status = int(not yes_no(vs[vs_flag]))
                if vs_flag_status != int(trigger['status']):
                    trigger_status = vs_flag_status
                    hosttriggers_updateset.append(
                        {
                            "triggerid": host_triggers_by_tag[vs_flag]['triggerid'],
                            "status": trigger_status
                        }
                    )

            # disable host if no triggers enabled
            if host_status != host['status']:
                host_updateset['status'] = host_status

            # hosttriggers_updateset = [{"as":"da"}]
            # hostinterface_updateset = {"as":"da"}
            # host_updateset = {"as":"da", "status":34}
            if hosttriggers_updateset:
                for updateset in hosttriggers_updateset:
                    try:
                        zapi.trigger.update(**updateset)
                    except ZabbixAPIException:
                        logger.exception(f'Failed to update Zabbix host {vs["visibleId"]} triggers.')
                    else:
                        logger.debug(f"Update set: {updateset}")
                        logger.info(f'Updated Zabbix host triggers {vs["visibleId"]}.')

            if hostinterface_updateset:
                try:
                    zapi.hostinterface.update(**hostinterface_updateset)
                except ZabbixAPIException:
                    logger.exception(f'Failed to update Zabbix host {vs["visibleId"]} interface.')
                else:
                    logger.debug(f"Update set: {hostinterface_updateset}")
                    logger.info(f'Updated Zabbix host interface {vs["visibleId"]}.')

            if host_updateset:
                host_updateset["hostid"] = host_id
                try:
                    result = zapi.host.update(**host_updateset)
                except ZabbixAPIException:
                    logger.exception(f'Failed to update Zabbix host {vs["visibleId"]}.')
                else:
                    logger.debug(f"Update set: {host_updateset}")
                    logger.info(f'Updated Zabbix host {vs["visibleId"]}.')


def cleanup_zabbix_hosts(zapi, zabbix_hosts, fnt_virtualservers_indexed):
    for host in zabbix_hosts:
        host_id = host["hostid"]
        # host["host"] not in fnt_virtualservers_indexed
        vs = fnt_virtualservers_indexed.get(host["host"], {})
        # don't delete if no data from FNT
        if fnt_virtualservers_indexed and (yes_no(vs.get("cSdiDeleted", "N")) or not vs):
            try:
                zapi.host.delete(host_id)
            except ZabbixAPIException:
                logger.exception(f'Failed to delete Zabbix host {host["host"]}.')
            else:
                logger.info(f'Deleted Zabbix host {host["host"]}.')


class VFZSync:
    def __init__(self):
        super().__init__()

        # Initiate vPoller
        try:
            self._vpoller = vPollerAPI(vpoller_endpoint=vfzsync.CONFIG["vpoller"]["endpoint"])
            self._vpoller.run(method="about", vc_host=vfzsync.CONFIG["vpoller"]["vc_host"])
        except vPollerException:
            message = "vPoller initialization failed"
            logger.exception(message)
            raise vPollerException(message)

        # Initiate FNT API
        try:
            self._command = FNTCommandAPI(
                url=vfzsync.CONFIG["command"]["url"],
                username=vfzsync.CONFIG["command"]["username"],
                password=vfzsync.CONFIG["command"]["password"],
            )
        except FNTNotAuthorized:
            message = "FNT Command authorization failed"
            logger.exception(message)
            raise FNTNotAuthorized(message)

        # Initiate ZabbixAPI
        try:
            self._zapi = ZabbixAPI(
                url=vfzsync.CONFIG["zabbix"]["url"],
                user=vfzsync.CONFIG["zabbix"]["username"],
                password=vfzsync.CONFIG["zabbix"]["password"],
            )
            self._zapi.session.verify = False
            zabbix_hostgroup_name = vfzsync.CONFIG["zabbix"]["hostgroup"]
            zabbix_hostgroup_id = get_zabbix_hostgroupid_by_name(self._zapi, zabbix_hostgroup_name)
            if not zabbix_hostgroup_id:
                zabbix_hostgroup_id = self._zapi.hostgroup.create(name=zabbix_hostgroup_name)
                logger.info(f"Created Zabbix host group {zabbix_hostgroup_name}.")

        except ZabbixAPIException:
            message = "Zabbix authorization failed"
            logger.exception(message)
            raise ZabbixAPIException(message)


    def run_sync(self):
        logger.info('Sync started.')
        self.run_vpoller_fnt_sync()
        stats = self.run_fnt_zabbix_sync()
        logger.info('Sync completed.')
        return stats


    def run_vpoller_fnt_sync(self):
        """ vPoller -> FNT """

        vpoller_vms, vpoller_vms_indexed = get_vpoller_vms(self._vpoller)
        fnt_virtualservers, fnt_virtualservers_indexed = get_fnt_vs(command=self._command, index="cUuid")

        sync_fnt_vs(self._command, vpoller_vms, fnt_virtualservers_indexed)

        cleanup_fnt_vs(self._command, fnt_virtualservers, vpoller_vms_indexed)


    def run_fnt_zabbix_sync(self):
        """ FNT -> Zabbix """

        FNT_ZABBIX_TRANSFORM_MAP = [
            ("id", "host"),
            ("visibleId", "name"),
            ("cCommunityName", "{$SNMP_COMMUNITY}"),
        ]

        fnt_virtualservers, fnt_virtualservers_indexed = get_fnt_vs(command=self._command, index="id")
        zabbix_hostgroup_id = get_zabbix_hostgroupid_by_name(self._zapi, vfzsync.CONFIG["zabbix"]["hostgroup"])
        zabbix_hosts, zabbix_hosts_indexed_by_host = get_zabbix_hosts(self._zapi, zabbix_hostgroup_id)

        sync_zabbix_hosts(
            self._zapi, fnt_virtualservers=fnt_virtualservers, zabbix_hosts_indexed_by_host=zabbix_hosts_indexed_by_host
        )

        # cleanup
        cleanup_zabbix_hosts(
            self._zapi, zabbix_hosts=zabbix_hosts, fnt_virtualservers_indexed=fnt_virtualservers_indexed
        )

        stats_new = len([vs for vs in fnt_virtualservers if yes_no(vs['cSdiNewServer'])])
        stats_deleted = len([vs for vs in fnt_virtualservers if yes_no(vs['cSdiDeleted']) and not yes_no(vs['cCSdiDelConfirmed'])])
        stats = {'vs_new': stats_new, 'vs_deleted': stats_deleted}
        return stats


logger = init_logger()
logger.debug(f'{__name__} init done.')
init_tracing()
