#!/bin/bash
# OMEGA GUARDIAN — full rewrite, every watchdog inside the loop, zero dead code
OMEGA_HOME="/data/data/com.termux/files/home"
LOGS="$OMEGA_HOME/omega_runtime/logs"
SSH_KEY="$OMEGA_HOME/.ssh/omega_bridge"
PHONE2="192.168.11.2"
_GUARDIAN_CYCLES=0
mkdir -p "$LOGS" "$OMEGA_HOME/omega_runtime/state"
echo "[$(date)] Guardian started (PID $$)" >> "$LOGS/guardian.log"

while true; do
    _GUARDIAN_CYCLES=$((_GUARDIAN_CYCLES + 1))

    if ! pgrep -f omega_v10.py > /dev/null; then
        echo "[$(date)] RESTART: omega_v10.py" >> "$LOGS/guardian.log"
        nohup python3 "$OMEGA_HOME/omega_v10.py" >> "$LOGS/nohup.log" 2>&1 &
        sleep 10
    fi
    if ! pgrep -f omega_consensus.py > /dev/null; then
        echo "[$(date)] RESTART: consensus" >> "$LOGS/guardian.log"
        OMEGA_NODE_ID=omega-node-001 OMEGA_NODE_HOST=192.168.11.115 \
        nohup python3 "$OMEGA_HOME/omega_consensus.py" >> "$LOGS/consensus.log" 2>&1 &
        sleep 3
    fi
    if ! pgrep -f omega_sentinel.py > /dev/null; then
        echo "[$(date)] RESTART: sentinel" >> "$LOGS/guardian.log"
        nohup python3 "$OMEGA_HOME/omega_sentinel.py" watch >> "$LOGS/sentinel.log" 2>&1 &
        sleep 2
    fi
    if ! pgrep -f omega_node_manager.py > /dev/null; then
        echo "[$(date)] RESTART: node_manager" >> "$LOGS/guardian.log"
        OMEGA_NODE_ID=omega-node-001 OMEGA_NODE_HOST=192.168.11.115 \
        nohup python3 "$OMEGA_HOME/omega_node_manager.py" >> "$LOGS/node_manager.log" 2>&1 &
        sleep 3
    fi
    if ! pgrep -f omega_spawn_engine.py > /dev/null; then
        echo "[$(date)] RESTART: spawn_engine" >> "$LOGS/guardian.log"
        nohup python3 "$OMEGA_HOME/omega_spawn_engine.py" watch >> "$LOGS/spawn_engine.log" 2>&1 &
    fi
    if ! pgrep -f omega_http_server.py > /dev/null; then
        echo "[$(date)] RESTART: node3 http_server" >> "$LOGS/guardian.log"
        nohup python3 "$OMEGA_HOME/omega_runtime/omega_http_server.py" >> "$LOGS/node3_http.log" 2>&1 &
        sleep 2
    fi
    if ! pgrep -f omega_companion_server.py > /dev/null; then
        echo "[$(date)] RESTART: companion_server" >> "$LOGS/guardian.log"
        nohup python3 "$OMEGA_HOME/omega_companion_server.py" >> "$LOGS/companion_server.log" 2>&1 &
    fi
    if ! pgrep -f omega_node3_bridge > /dev/null; then
        echo "[$(date)] RESTART: node3_bridge" >> "$LOGS/guardian.log"
        nohup python3 "$OMEGA_HOME/omega_node3_bridge.py" >> "$LOGS/node3_bridge.log" 2>&1 &
    fi
    if ! pgrep -f omega_dashboard_bridge.py > /dev/null; then
        echo "[$(date)] RESTART: dashboard_bridge" >> "$LOGS/guardian.log"
        nohup python3 "$OMEGA_HOME/omega_dashboard_bridge.py" >> "$LOGS/dashboard_bridge.log" 2>&1 &
    fi
    if ! pgrep -f "omega_provenance_api" > /dev/null 2>&1; then
        echo "[$(date)] RESTART: provenance_api" >> "$LOGS/guardian.log"
        nohup python3 "$OMEGA_HOME/omega_provenance_api.py" >> "$LOGS/provenance_api.log" 2>&1 &
    fi
    if ! pgrep -f "omega_tunnel_daemon" > /dev/null; then
        echo "[$(date)] RESTART: tunnel_daemon" >> "$LOGS/guardian.log"
        nohup bash "$OMEGA_HOME/omega_tunnel_daemon.sh" > /dev/null 2>&1 &
        sleep 8
    fi
    if ! pgrep -f "ssh.*omega_bridge" > /dev/null; then
        echo "[$(date)] RESTART: ssh_tunnel" >> "$LOGS/guardian.log"
        nohup ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no -o ServerAliveInterval=30 \
            -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes -L 5432:127.0.0.1:5432 \
            u0_a253@$PHONE2 -p 8022 -N >> "$LOGS/ssh_tunnel.log" 2>&1 &
        sleep 8
    fi
    if ! pgrep -f "localhost.run" > /dev/null; then
        nohup ssh -R 80:localhost:5004 -o StrictHostKeyChecking=no -o ServerAliveInterval=30 \
            -o ServerAliveCountMax=3 nokey@localhost.run >> "$LOGS/tunnel.log" 2>&1 &
        echo "[$(date)] RESTART: node3 localhost.run tunnel" >> "$LOGS/guardian.log"
    fi


    if ! pgrep -f "cloudflared tunnel --url http://127.0.0.1:8090" > /dev/null; then
        echo "[$(date)] RESTART: gallery cloudflared tunnel" >> "$LOGS/guardian.log"
        nohup cloudflared tunnel --url http://127.0.0.1:8090 > "$LOGS/cloudflared_gallery.log" 2>&1 &
        sleep 8
        bash "$OMEGA_HOME/omega_update_redirect.sh" >> "$LOGS/redirect_update.log" 2>&1
    fi

    if ! pgrep -f "cloudflared tunnel --url http://127.0.0.1:8082" > /dev/null; then
        echo "[$(date)] RESTART: API cloudflared tunnel" >> "$LOGS/guardian.log"
        nohup cloudflared tunnel --url http://127.0.0.1:8082 > "$LOGS/api_tunnel.log" 2>&1 &
        sleep 8
        bash "$OMEGA_HOME/omega_update_api_url.sh" >> "$LOGS/api_url_update.log" 2>&1
    fi

    # Check for silent URL drift even when the process never died
    bash "$OMEGA_HOME/omega_update_api_url.sh" >> "$LOGS/api_url_update.log" 2>&1

    NOW=$(date +%s)
    LAST=$(cat "$OMEGA_HOME/omega_runtime/state/last_storage_check" 2>/dev/null || echo 0)
    if [ $((NOW - LAST)) -gt 3600 ]; then
        python3 "$OMEGA_HOME/omega_storage_verify.py" >> "$LOGS/storage_verify.log" 2>&1
        echo $NOW > "$OMEGA_HOME/omega_runtime/state/last_storage_check"
    fi
    LAST=$(cat "$OMEGA_HOME/omega_runtime/state/last_dr_backup" 2>/dev/null || echo 0)
    if [ $((NOW - LAST)) -gt 86400 ]; then
        python3 "$OMEGA_HOME/omega_disaster_recovery.py" backup >> "$LOGS/disaster_recovery.log" 2>&1
        echo $NOW > "$OMEGA_HOME/omega_runtime/state/last_dr_backup"
    fi
    LAST=$(cat "$OMEGA_HOME/omega_runtime/state/last_deadman_check" 2>/dev/null || echo 0)
    if [ $((NOW - LAST)) -gt 3600 ]; then
        python3 "$OMEGA_HOME/omega_deadman_switch.py" >> "$LOGS/deadman.log" 2>&1
        echo $NOW > "$OMEGA_HOME/omega_runtime/state/last_deadman_check"
    fi
    LAST=$(cat "$OMEGA_HOME/omega_runtime/state/last_webhook_sync" 2>/dev/null || echo 0)
    if [ $((NOW - LAST)) -gt 300 ]; then
        python3 "$OMEGA_HOME/omega_webhook_sync.py" >> "$LOGS/webhook_sync.log" 2>&1
        echo $NOW > "$OMEGA_HOME/omega_runtime/state/last_webhook_sync"
    fi
    LAST=$(cat "$OMEGA_HOME/omega_runtime/state/last_ddns_update" 2>/dev/null || echo 0)
    if [ $((NOW - LAST)) -gt 3600 ]; then
        python3 "$OMEGA_HOME/omega_runtime/omega_ddns.py" >> "$LOGS/ddns.log" 2>&1
        echo $NOW > "$OMEGA_HOME/omega_runtime/state/last_ddns_update"
    fi

    if [ $((_GUARDIAN_CYCLES % 10)) -eq 0 ]; then
        python3 "$OMEGA_HOME/omega_oracle_v2.py" >> "$LOGS/oracle.log" 2>&1 &
    fi
    sleep 30
done
