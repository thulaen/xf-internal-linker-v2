#!/bin/sh
set -eu

while true; do
  interval="${SONAR_AUTOSCAN_INTERVAL_SECONDS:-1800}"
  retry_interval="${SONAR_AUTOSCAN_RETRY_SECONDS:-60}"
  until curl -fsS "$SONAR_HOST_URL/api/system/status" >/dev/null &&
    curl -fsS "$SONAR_HOST_URL/api/server/version" >/dev/null; do
    echo "waiting for sonarqube"
    sleep 10
  done

  rm -rf /tmp/sonar-src
  mkdir -p /tmp/sonar-src/backend /tmp/sonar-src/frontend
  cp -a /repo/backend/. /tmp/sonar-src/backend/
  cp -a /repo/frontend/. /tmp/sonar-src/frontend/
  cp /repo/sonar-project.properties /tmp/sonar-src/sonar-project.properties

  cd /tmp/sonar-src
  if sonar-scanner -Dsonar.host.url="$SONAR_HOST_URL" -Dsonar.token="$SONAR_TOKEN"; then
    sleep "$interval"
  else
    echo "scan failed, will retry next cycle"
    sleep "$retry_interval"
  fi
done
