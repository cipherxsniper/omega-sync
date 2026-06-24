#!/bin/bash
URL=$(grep -o 'https://[a-zA-Z0-9.-]*trycloudflare.com' ~/omega_runtime/logs/cloudflared_gallery.log | tail -1)
if [ -z "$URL" ]; then
  echo "No tunnel URL found — aborting"
  exit 1
fi
FULL_URL="${URL}/omega_gallery.html"
cat > ~/omega_redirect/index.html << HTML_END
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="0; url=${FULL_URL}">
<title>Omega Gallery</title>
<style>body{background:#0D0B0E;color:#C9A84C;font-family:monospace;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;text-align:center;}</style>
</head>
<body>
<div><p>Entering the Omega Gallery...</p><p><a href="${FULL_URL}" style="color:#C9A84C;">Click here if not redirected</a></p></div>
<script>window.location.replace("${FULL_URL}");</script>
</body>
</html>
HTML_END
cd ~/omega_redirect
git add index.html
git commit -m "Update redirect target: ${URL}"
git push origin main 2>&1 | tail -3
echo "Redirect updated to: ${FULL_URL}"
