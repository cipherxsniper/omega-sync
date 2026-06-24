#!/bin/bash
# OMEGA GUARDIAN — Watches and restarts everything
# Never lets the system die. Ever.

OMEGA_HOME="/data/data/com.termux/files/home"
LOGS="$OMEGA_HOME/omega_runtime/logs"
SSH_KEY="$OMEGA_HOME/.ssh/omega_bridge"
PHONE2="192.168.11.163"
_GUARDIAN_CYCLES=0

mkdir -p "$LOGS"

while true; do
    _GUARDIAN_CYCLES=$((_GUARDIAN_CYCLES + 1))

    # Watch omega_v10.py
    if ! pgrep -f omega_v10.py > /dev/null; then
        echo "[$(date)] RESTART: omega_v10.py" >> "$LOGS/guardian.log"
        nohup python3 "$OMEGA_HOME/omega_v10.py" \
          >> "$LOGS/nohup.log" 2>&1 &
        sleep 10
    fi

    # Watch consensus node
    if ! pgrep -f omega_consensus.py > /dev/null; then
        echo "[$(date)] RESTART: consensus node" >> "$LOGS/guardian.log"
        OMEGA_NODE_ID=omega-node-001 \
        OMEGA_NODE_HOST=192.168.11.115 \
        nohup python3 "$OMEGA_HOME/omega_consensus.py" \
          >> "$LOGS/consensus.log" 2>&1 &
        sleep 3
    fi

    # Watch sentinel
    if ! pgrep -f omega_sentinel.py > /dev/null; then
        echo "[$(date)] RESTART: sentinel" >> "$LOGS/guardian.log"
        nohup python3 "$OMEGA_HOME/omega_sentinel.py" watch \
          >> "$LOGS/sentinel.log" 2>&1 &
        sleep 2
    fi

    # Watch node manager
    if ! pgrep -f omega_node_manager.py > /dev/null; then
        echo "[$(date)] RESTART: node manager" >> "$LOGS/guardian.log"
        OMEGA_NODE_ID=omega-node-001 OMEGA_NODE_HOST=192.168.11.115 \
        nohup python3 "$OMEGA_HOME/omega_node_manager.py" \
          >> "$LOGS/node_manager.log" 2>&1 &
        sleep 3
        # Also restart node 002 on Phone 2
        ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no \
          -o ConnectTimeout=5 \
          u0_a253@$PHONE2 -p 8022 \
          "pgrep -f omega_node_manager || (OMEGA_NODE_ID=omega-node-002 OMEGA_NODE_HOST=192.168.11.2 nohup python3 ~/Omega-Production/omega_bank/omega_node_manager.py >> ~/omega_runtime/logs/node_manager.log 2>&1 &)" &
    fi

    # Watch tunnel daemon — self-healing SSH
    if ! pgrep -f "omega_tunnel_daemon" > /dev/null; then
        echo "[$(date)] RESTART: tunnel daemon" >> "$LOGS/guardian.log"
        nohup bash "$OMEGA_HOME/omega_tunnel_daemon.sh"           > /dev/null 2>&1 &
        sleep 8
    fi

    # Watch SSH tunnel — most critical link
    if ! pgrep -f "ssh.*omega_bridge" > /dev/null; then
        echo "[$(date)] RESTART: SSH tunnel" >> "$LOGS/guardian.log"
        nohup ssh -i "$SSH_KEY" \
          -o StrictHostKeyChecking=no \
          -o ServerAliveInterval=30 \
          -o ServerAliveCountMax=3 \
          -o ExitOnForwardFailure=yes \
          -L 5432:127.0.0.1:5432 \
          u0_a253@$PHONE2 -p 8022 -N \
          >> "$LOGS/ssh_tunnel.log" 2>&1 &
        sleep 8
        psql -h 127.0.0.1 -p 5432 -U postgres -d omega_bank \
          -c "SELECT 1" > /dev/null 2>&1 \
          && echo "[$(date)] SSH tunnel RESTORED" >> "$LOGS/guardian.log" \
          || echo "[$(date)] SSH tunnel FAILED" >> "$LOGS/guardian.log"
    fi

    # Run oracle every 5 minutes (10 cycles x 30s)
    if [ $((_GUARDIAN_CYCLES % 10)) -eq 0 ]; then
        python3 "$OMEGA_HOME/omega_oracle_v2.py" \
          >> "$LOGS/oracle.log" 2>&1 &
        bash "$OMEGA_HOME/omega_build_watcher.sh" >> "$LOGS/build_watcher.log" 2>&1 &
    fi

    bash "$OMEGA_HOME/omega_update_api_url.sh" >> "$LOGS/api_url_update.log" 2>&1
    sleep 30
done

# ── Spawn Engine — auto-grows network at thresholds ──────
if ! pgrep -f omega_spawn_engine.py > /dev/null; then
    echo "[$(date)] Spawn engine dead — restarting"
    nohup python3 /data/data/com.termux/files/home/omega_spawn_engine.py watch \
        >> /data/data/com.termux/files/home/omega_runtime/logs/spawn_engine.log 2>&1 &
fi

# SSH tunnel watchdog
pg_isready -h 127.0.0.1 -p 5432 -q 2>/dev/null || {
    pkill -f "ssh.*omega_bridge" 2>/dev/null
    sleep 2
    nohup ssh -i ~/.ssh/omega_bridge \
        -o StrictHostKeyChecking=no \
        -o ServerAliveInterval=20 \
        -o ServerAliveCountMax=3 \
        -o ExitOnForwardFailure=yes \
        -L 5432:127.0.0.1:5432 \
        u0_a253@192.168.11.2 \
        -p 8022 -N &
}
