#!/data/data/com.termux/files/usr/bin/bash
# find2 — Auto-finds Phone 2 and reconnects tunnel
# Usage: find2

echo "Scanning for Phone 2..."

FOUND=""
for i in $(seq 1 254); do
  ip="192.168.11.$i"
  result=$(ssh -i ~/.ssh/omega_bridge \
    -p 8022 \
    -o ConnectTimeout=2 \
    -o StrictHostKeyChecking=no \
    -o BatchMode=yes \
    u0_a253@$ip "echo OK" 2>/dev/null)
  if [ "$result" = "OK" ]; then
    FOUND=$ip
    echo "Phone 2 found at $FOUND"
    break
  fi
done

if [ -z "$FOUND" ]; then
  echo "Phone 2 not found on 192.168.11.1-20"
  echo "Go to Phone 2 and run: sshd"
  exit 1
fi

# Update tunnel if IP changed
CURRENT=$(grep -r "u0_a253@192" ~/omega_guardian.sh | grep -o '192\.168\.11\.[0-9]*' | head -1)
if [ "$FOUND" != "$CURRENT" ]; then
  echo "IP changed: $CURRENT -> $FOUND"
  echo "Updating all config files..."
  sed -i "s/$CURRENT/$FOUND/g" \
    ~/omega_disaster_recovery.py \
    ~/omega_node_manager.py \
    ~/omega_spawn_engine.py \
    ~/omega_storage_verify.py \
    ~/omega_treasury_cycle.py \
    ~/omega_v10.py \
    ~/omega_guardian.sh \
    ~/omega_start.sh \
    ~/omega_tunnel_daemon.sh \
    ~/omega_api.py \
    ~/omega_companion_server.py \
    ~/omega_deadman_switch.py
  echo "Config files updated"
fi

# Kill old tunnel
pkill autossh 2>/dev/null
sleep 2

# Restart tunnel
nohup autossh -M 0 \
  -i ~/.ssh/omega_bridge \
  -o StrictHostKeyChecking=no \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=6 \
  -o ExitOnForwardFailure=yes \
  -o TCPKeepAlive=yes \
  -L 5432:127.0.0.1:5432 \
  u0_a253@$FOUND -p 8022 -N > /dev/null 2>&1 &

sleep 3

# Restart consensus on Phone 2
echo "Starting consensus node-002..."
ssh -i ~/.ssh/omega_bridge -p 8022 \
  -o StrictHostKeyChecking=no \
  u0_a253@$FOUND \
  "pkill -f omega_consensus 2>/dev/null; sleep 1; nohup python3 ~/omega_consensus.py --node-id node-002 --port 7432 > ~/omega_runtime/logs/consensus_node2.log 2>&1 &" 2>/dev/null

sleep 2

# Test PostgreSQL
result=$(psql -h 127.0.0.1 -p 5432 -U postgres -d omega_ledger \
  -c "SELECT COUNT(*) FROM nft_registry;" 2>/dev/null | grep -o '[0-9]*' | head -1)

if [ "$result" = "400" ]; then
  echo "PostgreSQL OK — $result NFTs confirmed"
  echo "Tunnel stable at $FOUND"
  echo ""
  echo "Run: score"
else
  echo "PostgreSQL not responding — check Phone 2"
fi
