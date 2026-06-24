#!/data/data/com.termux/files/usr/bin/bash
# Watchdog for the NFT Provenance Verification API (port 8082)
LOG="$HOME/omega_runtime/logs/api_guardian.log"
mkdir -p "$HOME/omega_runtime/logs"
if ! pgrep -f "omega_provenance_api.py" > /dev/null 2>&1; then
    echo "[$(date -u)] API down, restarting..." >> "$LOG"
    nohup python3 "$HOME/omega_provenance_api.py" >> "$HOME/omega_runtime/logs/provenance_api.log" 2>&1 &
fi
