#!/bin/bash
set +e

# Script trace mode
if [ "${DEBUG_MODE}" == "true" ]; then
    set -o xtrace
fi

cd /app

DEFAULT_CONFIG=$(cat <<-END
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

END
)
if [ ! -f ./vzbx-sync.yaml ]; then
    echo "$DEFAULT_CONFIG" > ./vzbx-sync.yaml
fi

exec python ./vzbx-sync.py

#bash
