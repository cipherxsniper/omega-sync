#!/bin/bash
# ═══════════════════════════════════════════════════════
# OMEGA START — Full System Bootstrap
# One command. Everything live. Nothing manual ever again.
# ═══════════════════════════════════════════════════════

OMEGA_HOME="/data/data/com.termux/files/home"
LOGS="$OMEGA_HOME/omega_runtime/logs"
SSH_KEY="$OMEGA_HOME/.ssh/omega_bridge"
PHONE2="192.168.11.2"

echo "═══════════════════════════════════════════"
echo "  OMEGA SYSTEM BOOTSTRAP"
echo "  $(date)"
echo "═══════════════════════════════════════════"

mkdir -p "$LOGS"

# Run oracle BEFORE boot — establish baseline
pgrep -f crond > /dev/null || crond

echo "Running Oracle baseline..."
python3 "$OMEGA_HOME/omega_oracle_v2.py" 2>/dev/null | grep -E "SCORE|Grade|ISSUES"

# ── Step 1: Tunnel Daemon ──────────────────────────────
echo "[1/7] SSH Tunnel Daemon → Phone 2 PostgreSQL..."
pkill -f "omega_tunnel_daemon" 2>/dev/null
pkill -f "ssh.*omega_bridge" 2>/dev/null
sleep 1
nohup bash "$OMEGA_HOME/omega_tunnel_daemon.sh"   > /dev/null 2>&1 &
sleep 8
psql -h 127.0.0.1 -p 5432 -U postgres -d omega_bank   -c "SELECT 1" > /dev/null 2>&1   && echo "  ✅ PostgreSQL bridge ONLINE"   || { echo "  ⚠️  PostgreSQL bridge FAILED — running find2..."; bash ~/find2.sh; }

# ── Step 2: Consensus Node 001 ─────────────────────────
echo "[2/7] Consensus Node 001..."
pkill -f "omega_consensus.py" 2>/dev/null
sleep 1
OMEGA_NODE_ID=omega-node-001 \
OMEGA_NODE_HOST=192.168.11.115 \
nohup python3 "$OMEGA_HOME/omega_consensus.py" \
  > "$LOGS/consensus.log" 2>&1 &
sleep 3
pgrep -f omega_consensus.py > /dev/null \
  && echo "  ✅ Consensus Node 001 ONLINE" \
  || echo "  ⚠️  Consensus Node 001 FAILED"

# ── Step 3: Sentinel ───────────────────────────────────
echo "[3/7] Sentinel Watchdog..."
pkill -f "omega_sentinel.py" 2>/dev/null
sleep 1
nohup python3 "$OMEGA_HOME/omega_sentinel.py" watch \
  > "$LOGS/sentinel.log" 2>&1 &
sleep 2
pgrep -f omega_sentinel.py > /dev/null \
  && echo "  ✅ Sentinel ONLINE" \
  || echo "  ⚠️  Sentinel FAILED"

# ── Step 4: Omega AI v10 ───────────────────────────────
echo "[4/7] Omega AI v10 Engine..."
pkill -f "omega_v10.py" 2>/dev/null
sleep 2
nohup python3 "$OMEGA_HOME/omega_v10.py" \
  > "$LOGS/nohup.log" 2>&1 &
sleep 8
pgrep -f omega_v10.py > /dev/null \
  && echo "  ✅ Omega AI v10 ONLINE" \
  || echo "  ❌ Omega AI v10 FAILED"

# ── Step 5: Node Manager ───────────────────────────────
echo "[5/7] Node Manager..."
pkill -f omega_node_manager.py 2>/dev/null
sleep 1
OMEGA_NODE_ID=omega-node-001 OMEGA_NODE_HOST=192.168.11.115 \
nohup python3 "$OMEGA_HOME/omega_node_manager.py" \
  > "$LOGS/node_manager.log" 2>&1 &
sleep 3
pgrep -f omega_node_manager.py > /dev/null \
  && echo "  ✅ Node Manager ONLINE" \
  || echo "  ⚠️  Node Manager FAILED"

# ── Step 6: Node 002 on Phone 2 ───────────────────────
echo "[6/7] Node 002 on Phone 2..."
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no \
  -o ConnectTimeout=10 \
  u0_a253@$PHONE2 -p 8022 \
  "pgrep -f omega_node_manager > /dev/null && echo OK || (export OMEGA_NODE_ID=omega-node-002; export OMEGA_NODE_HOST=192.168.11.2; setsid python3 ~/Omega-Production/omega_bank/omega_node_manager.py >> ~/omega_runtime/logs/node_manager.log 2>&1 </dev/null &amp; sleep 8 && pgrep -f omega_node_manager > /dev/null && echo OK)" \
  && echo "  ✅ Node 002 ONLINE" \
  || echo "  ⚠️  Node 002 FAILED"

# ── Step 7: Guardian ───────────────────────────────────
echo "[7/8] Guardian Watchdog..."
pkill -f "omega_guardian.sh" 2>/dev/null
sleep 1
nohup bash "$OMEGA_HOME/omega_guardian.sh" \
  > /dev/null 2>&1 &
echo "  ✅ Guardian ONLINE"

# ── Step 8: Node 3 Omega Cloud ────────────────────────
echo "[8/8] Node 3 Omega Cloud..."
pkill -f omega_http_server.py 2>/dev/null
pkill -f omega_tls_server.py 2>/dev/null
sleep 1
nohup python3 "$OMEGA_HOME/omega_runtime/omega_tls_server.py" \
    >> "$LOGS/node3.log" 2>&1 &
nohup python3 "$OMEGA_HOME/omega_runtime/omega_http_server.py" \
    >> "$LOGS/node3_http.log" 2>&1 &
sleep 2
curl -s http://127.0.0.1:5004/health > /dev/null 2>&1 \
    && echo "  ✅ Node 3 ONLINE" \
    || echo "  ⚠️  Node 3 FAILED"

# ── Status Board ───────────────────────────────────────
sleep 3
echo ""
echo "═══════════════════════════════════════════"
echo "  OMEGA SYSTEM STATUS"
echo "═══════════════════════════════════════════"
pgrep -f omega_v10.py       > /dev/null && echo "  🟢 omega_v10.py      RUNNING" || echo "  🔴 omega_v10.py      DEAD"
pgrep -f omega_consensus.py > /dev/null && echo "  🟢 consensus node    RUNNING" || echo "  🔴 consensus node    DEAD"
pgrep -f omega_sentinel.py  > /dev/null && echo "  🟢 sentinel          RUNNING" || echo "  🔴 sentinel          DEAD"
pgrep -f omega_node_manager > /dev/null && echo "  🟢 node manager      RUNNING" || echo "  🔴 node manager      DEAD"
pgrep -f omega_guardian.sh  > /dev/null && echo "  🟢 guardian          RUNNING" || echo "  🔴 guardian          DEAD"
pgrep -f "ssh.*omega_bridge" > /dev/null && echo "  🟢 SSH tunnel        RUNNING" || echo "  🔴 SSH tunnel        DEAD"
pgrep -f omega_http_server.py > /dev/null && echo "  🟢 node 3 cloud      RUNNING" || echo "  🔴 node 3 cloud      DEAD"
echo "═══════════════════════════════════════════"
echo ""
echo "  Telegram: /start"
echo "  Logs: $LOGS/"
echo "═══════════════════════════════════════════"

# Run oracle AFTER boot — prove system is still perfect
echo ""
echo "Running Oracle post-boot verification..."
python3 "$OMEGA_HOME/omega_oracle_v2.py" 2>/dev/null | grep -E "SCORE|Grade|ISSUES|PERFECT"

echo "═══════════════════════════════════════════"
echo "  RESTART STABILITY REPORT"
echo "═══════════════════════════════════════════"
python3 ~/omega_restart_tracker.py
echo "═══════════════════════════════════════════"
