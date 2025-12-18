#!/usr/bin/env bash

# Define servers: name -> user@host
declare -A SERVERS=(
  [dev-db]="db-test-smartdorm-V2.schollheim.net"
  [dev-api]="smartdormv2-api-dev.schollheim.net"
  [dev-frontend]="smartdormv2-dev.schollheim.net"
  [prod-db]="db-smartdorm.schollheim.net"
  [prod_api]="api-smartdormv2-dmz.schollheim.net"
  [prod_frontend]="web-smartdormv2-dmz.schollheim.net"

)

PS3="Select server: "

select name in "${!SERVERS[@]}" "Quit"; do
  if [[ "$name" == "Quit" ]]; then
    exit 0
  elif [[ -n "$name" ]]; then
    echo "Connecting to $name (${SERVERS[$name]})..."
    ssh "${SERVERS[$name]}"
    break
  else
    echo "Invalid selection"
  fi
done
