#!/data/data/com.termux/files/usr/bin/bash
# omega_deploy.sh — pulls from omega-sync and deploys
OMEGA_HOME="/data/data/com.termux/files/home"
SYNC="$OMEGA_HOME/omega-sync"
BOT_TOKEN=$(grep "TELEGRAM_BOT_TOKEN" "$OMEGA_HOME/.env" | cut -d= -f2 | tr -d " ")
CHAT_ID=$(grep "TELEGRAM_CHAT_ID" "$OMEGA_HOME/.env" | cut -d= -f2 | tr -d " ")
notify() { curl -s -X POST "https://api.telegram.org/bot$BOT_TOKEN/sendMessage" -d chat_id="$CHAT_ID" -d text="$1" > /dev/null; }
notify "⚙️ Deploying build..."
cd "$SYNC" && git pull origin master --force 2>/dev/null
cp "$SYNC/phone1/"*.py "$OMEGA_HOME/" 2>/dev/null
cp "$SYNC/phone1/"*.sh "$OMEGA_HOME/" 2>/dev/null
cp "$SYNC/phone1/"*.html "$OMEGA_HOME/" 2>/dev/null
[ -f "$SYNC/NEXT_BUILD.md" ] && RUN=$(grep "^RUN:" "$SYNC/NEXT_BUILD.md" | cut -d: -f2- | tr -d " ")
if [ -n "$RUN" ]; then
    notify "▶️ Running: $RUN"
    cd "$OMEGA_HOME" && eval "$RUN" >> "$OMEGA_HOME/omega_runtime/logs/deploy.log" 2>&1
fi
SCORE=$(export PGPASSWORD=omega && python3 "$OMEGA_HOME/omega_oracle_v2.py" score 2>/dev/null | grep "SYSTEM SCORE" | head -1)
notify "✅ Deploy complete. $SCORE"
echo "[$(date)] Deploy complete" >> "$OMEGA_HOME/omega_runtime/logs/deploy.log"
