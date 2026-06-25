#!/bin/bash
LOG_URL=$(grep -o 'https://[a-zA-Z0-9.-]*trycloudflare.com' ~/omega_runtime/logs/cloudflared_api.log | tail -1)

if [ -z "$LOG_URL" ]; then
  echo "$(date -u) No URL found in cloudflared_api.log — skipping"
  exit 1
fi

CURRENT_URL=$(grep -o "var API_URL = '[^']*'" ~/omega_gallery.html | head -1 | sed "s/var API_URL = '//;s/'//")

if [ "$LOG_URL" = "$CURRENT_URL" ]; then
  exit 0
fi

HEALTH=$(curl -s -m 5 "${LOG_URL}/health")
if [[ "$HEALTH" != *"online"* ]]; then
  echo "$(date -u) New URL ${LOG_URL} not yet healthy — skipping this cycle"
  exit 1
fi

sed -i "s|var API_URL = '[^']*'|var API_URL = '${LOG_URL}'|" ~/omega_gallery.html
echo "$(date -u) API_URL drift detected and corrected: ${CURRENT_URL} -> ${LOG_URL}"
