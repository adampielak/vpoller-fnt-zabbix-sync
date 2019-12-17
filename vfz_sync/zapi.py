from debugtoolkit import (
    deflogger,
    dry_request,
    measure,
    init_logger
)


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
def get_zabbix_proxyid_by_name(zapi, name):
    return int(zapi.proxy.get(filter={"host": name})[0]["proxyid"])


@deflogger
def get_zabbix_host_triggers(zapi, hostids):
    triggers = zapi.trigger.get(
        hostids=hostids,
        output=["description", "status"],
        selectTags="extend"
    )
    for trigger in triggers:
        for tag in trigger['tags']:
            if tag['tag'] == 'FNT_Flag':
                trigger['tag'] = tag['value']
    # tag_flag = [tag['value'] for trigger in triggers for tag in trigger['tags'] if tag['tag'] == 'FNT_Flag']
    triggers_indexed_by_tag = {trigger['tag']: trigger for trigger in triggers if trigger.get('tag')}
    return triggers, triggers_indexed_by_tag

logger = init_logger()
