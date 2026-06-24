#!/usr/bin/env python3
"""
Omega URL Broker v2 — Auto-detects live Cloudflare tunnel URLs
from log files. No hardcoded URLs. Gallery and API tracked separately.
"""
import json, re, os, threading, time
from http.server import HTTPServer, BaseHTTPRequestHandler

GALLERY_LOG = "/data/data/com.termux/files/home/omega_runtime/logs/cloudflared_gallery.log"
API_LOG     = "/data/data/com.termux/files/home/omega_runtime/logs/cloudflared_api.log"
FALLBACK_API     = "https://pursue-carriers-humanities-shipped.trycloudflare.com"
FALLBACK_GALLERY = "https://investigated-blah-auditor-lightbox.trycloudflare.com"

URL_PATTERN = re.compile(r'https://[a-z0-9\-]+\.trycloudflare\.com')

state = {
    "api":     FALLBACK_API,
    "gallery": FALLBACK_GALLERY,
    "api_updated":     "startup",
    "gallery_updated": "startup",
}

def extract_url(log_path):
    """Read log file and return the most recent trycloudflare URL."""
    if not os.path.exists(log_path):
        return None
    try:
        with open(log_path, "r") as f:
            lines = f.readlines()
        # Search from bottom up for a URL line (not an error)
        for line in reversed(lines):
            if "ERR" in line or "error" in line.lower():
                continue
            match = URL_PATTERN.search(line)
            if match:
                return match.group(0)
    except Exception:
        pass
    return None

def refresh_urls():
    """Poll log files every 30s and update state."""
    while True:
        api_url = extract_url(API_LOG)
        if api_url:
            state["api"] = api_url
            state["api_updated"] = time.strftime("%H:%M:%S")

        gallery_url = extract_url(GALLERY_LOG)
        if gallery_url:
            state["gallery"] = gallery_url
            state["gallery_updated"] = time.strftime("%H:%M:%S")

        time.sleep(30)

class BrokerHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/current-api":
            self.send_json({"api": state["api"], "updated": state["api_updated"]})
        elif self.path == "/current-gallery":
            self.send_json({"gallery": state["gallery"], "updated": state["gallery_updated"]})
        elif self.path == "/current-all":
            self.send_json({
                "api":     state["api"],
                "gallery": state["gallery"],
                "api_updated":     state["api_updated"],
                "gallery_updated": state["gallery_updated"],
            })
        elif self.path == "/health":
            self.send_json({"status": "online", "api": state["api"], "gallery": state["gallery"]})
        else:
            self.send_response(404)
            self.end_headers()

    def send_json(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass

if __name__ == "__main__":
    # Initial URL detection
    api_url = extract_url(API_LOG)
    if api_url:
        state["api"] = api_url
    gallery_url = extract_url(GALLERY_LOG)
    if gallery_url:
        state["gallery"] = gallery_url

    # Start background refresh thread
    t = threading.Thread(target=refresh_urls, daemon=True)
    t.start()

    print(f"URL Broker v2 on :8085")
    print(f"  Gallery: {state['gallery']}")
    print(f"  API:     {state['api']}")

    server = HTTPServer(("127.0.0.1", 8085), BrokerHandler)
    server.serve_forever()
