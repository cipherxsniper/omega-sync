#!/data/data/com.termux/files/usr/bin/bash
# omega_build_watcher.sh — watches omega-sync for Claude commits
# Sends Telegram notification, waits for PUSH reply, deploys
OMEGA_HOME="/data/data/com.termux/files/home"
SYNC="$OMEGA_HOME/omega-sync"
STATE="$OMEGA_HOME/omega_runtime/state/last_sync_hash"
BOT_TOKEN=$(grep "TELEGRAM_BOT_TOKEN" "$OMEGA_HOME/.env" | cut -d= -f2 | tr -d " ")
CHAT_ID=$(grep "TELEGRAM_CHAT_ID" "$OMEGA_HOME/.env" | cut -d= -f2 | tr -d " ")
cd "$SYNC" || exit 1
git fetch origin master --quiet 2>/dev/null
REMOTE_HASH=$(git rev-parse origin/master 2>/dev/null)
LOCAL_HASH=$(cat "$STATE" 2>/dev/null || echo "")
if [ "$REMOTE_HASH" = "$LOCAL_HASH" ]; then exit 0; fi
MSG=$(git log origin/master..HEAD --oneline 2>/dev/null | head -3)
[ -z "$MSG" ] && MSG=$(git log origin/master -1 --pretty="%s" 2>/dev/null)
BUILD_DESC=""
[ -f "$SYNC/NEXT_BUILD.md" ] && BUILD_DESC=$(cat "$SYNC/NEXT_BUILD.md" 2>/dev/null | head -10)
NOTIFY="🔨 NEW BUILD READY\n\n$MSG\n\n$BUILD_DESC\n\nReply PUSH to deploy or SKIP to ignore."
curl -s -X POST "https://api.telegram.org/bot$BOT_TOKEN/sendMessage" \
  -d chat_id="$CHAT_ID" \
  -d text="$NOTIFY" \
  -d parse_mode="HTML" > /dev/null
echo "$REMOTE_HASH" > "$STATE"
echo "[$(date)] New build detected: $REMOTE_HASH" >> "$OMEGA_HOME/omega_runtime/logs/build_watcher.log"
# PUSH listener — checks for PUSH reply in Telegram
LAST_UPDATE=$(cat "$OMEGA_HOME/omega_runtime/state/last_tg_update" 2>/dev/null || echo 0)
UPDATES=$(curl -s "https://api.telegram.org/bot$BOT_TOKEN/getUpdates?offset=$LAST_UPDATE&limit=10&timeout=5")
echo "$UPDATES" | python3 -c "
import json,sys,os,subprocess
data = json.load(sys.stdin)
updates = data.get("result", [])
state = "/data/data/com.termux/files/home/omega_runtime/state"
for u in updates:
    uid = u["update_id"]
    text = u.get("message",{}).get("text","").strip().upper()
    open(f"{state}/last_tg_update","w").write(str(uid+1))
    if text == "PUSH":
        subprocess.run(["bash","/data/data/com.termux/files/home/omega_deploy.sh"])
    elif text == "SKIP":
        print("SKIP received")
" 2>/dev/null
