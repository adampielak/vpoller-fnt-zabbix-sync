#!/bin/bash
set +e

# Script trace mode
if [ "${DEBUG_MODE}" == "true" ]; then
    set -o xtrace
fi

cd /home/app/vfzsync

if [ ! -d ./config ]; then
    mkdir config
fi

if [ ! -d ./log ]; then
    mkdir log
fi

DEFAULT_CONFIG=$(cat <<-END
general:
  debug: ${GENERAL_DEBUG}
  dryrun: ${GENERAL_DRYRUN}
  trace: ${GENERAL_TRACE}
  interval: ${GENERAL_INTERVAL}
  loops: ${GENERAL_LOOPS}

vpoller:
  endpoint: ${VPOLLER_ENDPOINT}
  vc_host: ${VPOLLER_VC_HOST}

zabbix:
  url: ${ZABBIX_URL}
  username: ${ZABBIX_USERNAME}
  password: ${ZABBIX_PASSWORD}
  hostgroup: ${ZABBIX_HOSTGROUP}
  template: ${ZABBIX_TEMPLATE}
  proxy: ${ZABBIX_PROXY}

command:
  url: ${COMMAND_URL}
  username: ${COMMAND_USERNAME}
  password: ${COMMAND_PASSWORD}

logging:
  version: 1
  formatters:
    simple:
      format: '%(asctime)s:%(name)s:%(levelname)s:%(message)s'
  handlers:
    console:
      class: logging.StreamHandler
      level: DEBUG
      formatter: simple
      stream: ext://sys.stderr
    file:
      class: logging.FileHandler
      level: ERROR
      formatter: simple
      filename: <defined_in_code.log>
  loggers:
    vfzsync:
      level: DEBUG
      handlers: [console, file]
      propagate: no
    pyzabbix:
      level: INFO
      handlers: [console, file]
      propagate: no
    requests.packages.urllib3:
      level: WARN
      handlers: [console, file]
      propagate: yes
  root:
    level: WARN
    handlers: [console, file]

END
)
if [ ! -f ./config/vfzsync.yaml ]; then
    echo "$DEFAULT_CONFIG" > ./config/vfzsync.yaml
fi

# export FLASK_APP=vfz_webapp.py
# exec python -m flask run --host=0.0.0.0
exec gunicorn -b :5000 --access-logfile - --error-logfile - vfz_webapp:app

#bash
