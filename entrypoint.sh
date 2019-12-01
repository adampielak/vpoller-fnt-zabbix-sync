#!/bin/bash
set +e

# Script trace mode
if [ "${DEBUG_MODE}" == "true" ]; then
    set -o xtrace
fi

cd /app/vfz_sync

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
    vfz_sync:
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
if [ ! -f ./vfz_sync.yaml ]; then
    echo "$DEFAULT_CONFIG" > ./vfz_sync.yaml
fi

exec python ./vfz_sync.py

#bash
