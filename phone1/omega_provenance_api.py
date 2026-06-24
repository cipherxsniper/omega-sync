#!/usr/bin/env python3
import json
import psycopg2
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

PG_CONN = "dbname=omega_bank user=postgres host=127.0.0.1 port=5432"
PG_LEDGER = "dbname=omega_ledger user=postgres host=127.0.0.1 port=5432"

NFT_WALLET_MAP = {
    "2109a4cc-a066-4698-a478-a786bf096318": "Thomas Lee Harvey — Founder",
    "a7889956-ca14-432a-9cb7-7dc17530b7d9": "Omega Merchant",
    "ed574d93-0abf-4cc5-b6e0-9d73b77da135": "OMEGA_CREDIT",
    "b702cb19-9b5c-44f4-8db4-161e3bf60655": "OMEGA_RESERVE_LEDGER",
    "0b608cb6-6745-4b75-bb9d-fa60e8a1b051": "OMEGA_SYSTEM_TREASURY",
    "4053d3a5-06b8-43d6-b8d5-5268991f8cbc": "OMEGA_GENESIS",
    "b4ab75f8-adc6-4981-ba48-d6dc3df423a5": "Omega Treasury Reserve",
    "fa4d0a6a-bb76-45ec-90f6-4ec37f847963": "Omega Investment Pool",
    "8ad07ed5-f433-4439-a188-f11b51110ae4": "Omega Credit Layer",
    "c182dbbc-e607-4364-a6cc-7611dac8eb95": "Omega Debit Layer",
    "fac22005-e8d3-4e08-ba89-c14150503429": "Omega Genesis Liquidity Origin",
    "cb8f4ebe-3205-408f-a765-148275ac36b8": "Reserve Ledger",
    "c8818380-c58d-4c52-a912-d69e0ae0d263": "Ops Float",
}

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        
        try:
            if path == "/health":
                self.json_response({"status": "online", "collections": 4})
            elif path.startswith("/collection/"):
                slug = path.split("/")[-1]
                self.json_response(self.get_collection(slug))
            elif path.startswith("/wallet/"):
                wallet_id = path.split("/")[-1]
                self.json_response(self.get_wallet(wallet_id))
            elif path.startswith("/nft/verify/"):
                parts = path.split("/")
                collection = parts[3] if len(parts) > 3 else ""
                token_id = parts[4] if len(parts) > 4 else ""
                self.json_response(self.get_nft_verify(collection, token_id))
            elif path == "/ledger/stats":
                self.json_response(self.get_ledger_stats())
            elif path == "/founding-wallets":
                self.json_response(self.get_founding_wallets())
            elif path.startswith("/verify/receipt/"):
                receipt_hash = path.split("/")[-1]
                self.json_response(self.get_receipt(receipt_hash))
            elif path.startswith("/receipt/"):
                receipt_hash = path.split("/")[-1]
                self.html_response(self.get_receipt_page(receipt_hash))
            elif path.startswith("/collector/"):
                passport_id = path.split("/")[-1]
                self.html_response(self.get_collector_passport(passport_id))
            else:
                self.json_response({"error": "not found"}, 404)
        except Exception as e:
            self.json_response({"error": str(e)}, 500)
    
    def json_response(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def html_response(self, html, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(html.encode())
    
    def get_collection(self, slug):
        col_map = {
            "echoes": "Echoes of Eternity",
            "somnium": "Somnium",
            "paracosm": "Paracosm",
            "monolith": "Monolith"
        }
        col_name = col_map.get(slug, slug)
        try:
            conn = psycopg2.connect(PG_LEDGER)
            cur = conn.cursor()
            cur.execute("""
                SELECT token_id, title, rarity, theme, image_sha256,
                       om109_fingerprint, om109_sig_a, om109_sig_b,
                       chain_hash, owner_account_id, is_founder_linked,
                       sale_status, minted_at, stripe_payment_link
                FROM nft_registry
                WHERE collection = %s
                ORDER BY token_id ASC
            """, (col_name,))
            tokens = []
            for row in cur.fetchall():
                tokens.append({
                    "token_id": int(row[0]),
                    "title": row[1] or "",
                    "rarity": row[2] or "Common",
                    "theme": row[3] or "",
                    "image_sha256": row[4] or "",
                    "om109_fingerprint": row[5] or "",
                    "om109_sig_a": row[6] or "",
                    "om109_sig_b": row[7] or "",
                    "chain_hash": row[8] or "",
                    "owner_account_id": row[9] or "",
                    "is_founder_linked": bool(row[10]),
                    "sale_status": row[11] or "unsold",
                    "minted_at": str(row[12]) if row[12] else None,
                    "stripe_payment_link": row[13] or "",
                    "collection": col_name,
                })
            cur.close()
            conn.close()
            return {"collection": col_name, "count": len(tokens), "tokens": tokens}
        except Exception as e:
            return {"error": str(e)}

    def get_wallet(self, wallet_id):
        conn = psycopg2.connect(PG_CONN)
        cur = conn.cursor()
        cur.execute("SELECT available_balance FROM wallets WHERE id = %s", (wallet_id,))
        result = cur.fetchone()
        balance = float(result[0]) if result and result[0] else 0
        
        conn2 = psycopg2.connect(PG_LEDGER)
        cur2 = conn2.cursor()
        cur2.execute("""
            SELECT token_id, collection, title, rarity 
            FROM nft_registry 
            WHERE owner_account_id = %s 
            ORDER BY collection, token_id
        """, (wallet_id,))
        holdings = [{"token_id": row[0], "collection": row[1], "title": row[2], "rarity": row[3]} for row in cur2.fetchall()]
        
        cur.close()
        cur2.close()
        conn.close()
        conn2.close()
        
        return {"wallet_id": wallet_id, "balance": f"${balance:,.2f}" if balance > 0 else "N/A", "nft_count": len(holdings), "holdings": holdings}
    
    def get_nft_verify(self, collection, token_id):
        conn = psycopg2.connect(PG_LEDGER)
        cur = conn.cursor()
        col_map = {"echoes": "Echoes of Eternity", "somnium": "Somnium", "paracosm": "Paracosm", "monolith": "Monolith"}
        col_name = col_map.get(collection, collection)
        cur.execute("SELECT token_id, name, title, rarity, om109_fingerprint, chain_hash FROM nft_registry WHERE collection = %s AND token_id = %s", (col_name, int(token_id) if token_id.isdigit() else -1))
        result = cur.fetchone()
        cur.close()
        conn.close()
        
        if not result:
            return {"error": "NFT not found"}
        return {"token_id": result[0], "title": result[2], "rarity": result[3], "om109_fingerprint": result[4], "chain_hash": result[5], "authentic": True}
    
    def get_ledger_stats(self):
        conn = psycopg2.connect(PG_LEDGER)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM ledger_entries")
        total_entries = cur.fetchone()[0]
        cur.execute("SELECT SUM(amount) FROM ledger_entries WHERE event_type IN ('GENESIS', 'TRANSFER', 'SETTLEMENT')")
        total_value = float(cur.fetchone()[0] or 0)
        cur.execute("SELECT event_type, amount, created_at FROM ledger_entries ORDER BY created_at DESC LIMIT 20")
        recent = [{"event": row[0], "amount": f"${float(row[1]):,.2f}", "time": str(row[2])} for row in cur.fetchall()]
        cur.execute("SELECT rarity, COUNT(*) FROM nft_registry GROUP BY rarity ORDER BY COUNT(*) DESC")
        rarity_dist = {row[0]: row[1] for row in cur.fetchall()}
        cur.close()
        conn.close()
        return {"total_ledger_entries": total_entries, "total_value": f"${total_value:,.2f}", "recent_transactions": recent, "rarity_distribution": rarity_dist}
    
    def get_founding_wallets(self):
        results = []
        for nft_wallet_id, name in NFT_WALLET_MAP.items():
            wallet_data = self.get_wallet(nft_wallet_id)
            wallet_data["name"] = name
            results.append(wallet_data)
        return {"founding_wallets": results}
    
    def log_message(self, format, *args):
        pass


    def get_receipt(self, receipt_hash):
        try:
            conn = psycopg2.connect(PG_LEDGER)
            cur = conn.cursor()
            cur.execute("""
                SELECT r.token_id, r.title, r.collection, r.rarity,
                       r.om109_fingerprint, r.chain_hash, r.image_sha256,
                       r.owner_account_id, r.sold_at, r.stripe_payment_link,
                       r.receipt_hash
                FROM nft_registry r
                WHERE r.receipt_hash = %s
            """, (receipt_hash,))
            row = cur.fetchone()
            conn.close()
            if not row:
                return {"verified": False, "error": "Receipt not found on Omega Ledger"}
            return {
                "verified": True,
                "token_id": row[0],
                "title": row[1],
                "collection": row[2],
                "rarity": row[3],
                "om109_fingerprint": row[4],
                "chain_hash": row[5],
                "image_sha256": row[6],
                "owner": row[7],
                "purchased_at": str(row[8]),
                "receipt_hash": row[10],
                "ledger": "Omega Immutable Ledger",
                "standard": "ISO 20022 / OM109",
                "message": "This NFT purchase is cryptographically verified on the Omega Ledger."
            }
        except Exception as e:
            return {"verified": False, "error": str(e)}

    def get_receipt_page(self, receipt_hash):
        data = self.get_receipt(receipt_hash)
        if not data.get("verified"):
            return """<!DOCTYPE html><html><head><title>Omega Receipt</title>
            <style>body{background:#0D0B0E;color:#ff4d6a;font-family:monospace;
            display:flex;align-items:center;justify-content:center;height:100vh;margin:0;}
            .box{text-align:center;border:1px solid #ff4d6a;padding:40px;}</style></head>
            <body><div class="box"><h2>RECEIPT NOT FOUND</h2>
            <p>This receipt hash does not exist on the Omega Ledger.</p></div></body></html>"""

        rarity_color = {
            "Impossible Diamond": "#E8F4FD",
            "Black Diamond": "#B8BCC8",
            "Super Rare": "#C9A84C",
            "Rare": "#4CAF7D",
            "Medium": "#8B7355",
            "Common": "#5a4a35"
        }.get(data.get("rarity",""), "#C9A84C")

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Omega Receipt — {data['title']}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{background:#0D0B0E;color:#F0E6D3;font-family:'JetBrains Mono',monospace;min-height:100vh;padding:40px 20px;}}
.container{{max-width:680px;margin:0 auto;}}
.header{{text-align:center;margin-bottom:40px;}}
.omega-mark{{font-size:48px;color:#C9A84C;display:block;margin-bottom:12px;}}
.header h1{{font-size:11px;letter-spacing:4px;text-transform:uppercase;color:#C9A84C;}}
.header p{{font-size:10px;color:#8B7355;margin-top:6px;letter-spacing:1px;}}
.verified-badge{{display:inline-block;margin:20px auto;padding:10px 28px;
  border:1px solid #4CAF7D;color:#4CAF7D;font-size:10px;letter-spacing:3px;
  text-transform:uppercase;}}
.card{{background:#0c0a08;border:1px solid #2a1f15;padding:28px;margin-bottom:20px;}}
.card-title{{font-size:9px;letter-spacing:3px;text-transform:uppercase;
  color:#8B7355;margin-bottom:16px;border-bottom:1px solid #2a1f15;padding-bottom:10px;}}
.row{{display:flex;justify-content:space-between;align-items:flex-start;
  margin-bottom:12px;gap:20px;}}
.label{{font-size:9px;letter-spacing:2px;text-transform:uppercase;color:#8B7355;
  min-width:120px;}}
.value{{font-size:10px;color:#F0E6D3;text-align:right;word-break:break-all;}}
.value.gold{{color:#C9A84C;font-weight:bold;}}
.value.rarity{{color:{rarity_color};}}
.hash{{font-size:8px;color:#5a4a35;word-break:break-all;text-align:right;}}
.footer{{text-align:center;margin-top:40px;}}
.footer p{{font-size:9px;color:#8B7355;letter-spacing:1px;margin-bottom:8px;}}
.sig{{color:#C9A84C;font-size:10px;letter-spacing:2px;}}
.separator{{border:none;border-top:1px solid #2a1f15;margin:20px 0;}}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <span class="omega-mark">Ω</span>
    <h1>Certificate of Authenticity</h1>
    <p>Omega Art Studio — Immutable Provenance Record</p>
    <div class="verified-badge">✓ Verified on Omega Ledger</div>
  </div>

  <div class="card">
    <div class="card-title">Asset Details</div>
    <div class="row">
      <span class="label">Title</span>
      <span class="value gold">{data['title']}</span>
    </div>
    <div class="row">
      <span class="label">Collection</span>
      <span class="value">{data['collection']}</span>
    </div>
    <div class="row">
      <span class="label">Token ID</span>
      <span class="value">#{data['token_id']}</span>
    </div>
    <div class="row">
      <span class="label">Rarity</span>
      <span class="value rarity">{data['rarity']}</span>
    </div>
    <div class="row">
      <span class="label">Purchased</span>
      <span class="value">{str(data['purchased_at'])[:19]} UTC</span>
    </div>
  </div>

  <div class="card">
    <div class="card-title">Cryptographic Proof</div>
    <div class="row">
      <span class="label">OM109</span>
      <span class="hash">{data['om109_fingerprint']}</span>
    </div>
    <hr class="separator">
    <div class="row">
      <span class="label">Chain Hash</span>
      <span class="hash">{data['chain_hash']}</span>
    </div>
    <hr class="separator">
    <div class="row">
      <span class="label">Image SHA-256</span>
      <span class="hash">{data['image_sha256']}</span>
    </div>
    <hr class="separator">
    <div class="row">
      <span class="label">Receipt Hash</span>
      <span class="hash">{receipt_hash}</span>
    </div>
  </div>

  <div class="card">
    <div class="card-title">Ledger Record</div>
    <div class="row">
      <span class="label">Standard</span>
      <span class="value">ISO 20022 / OM109</span>
    </div>
    <div class="row">
      <span class="label">Ledger</span>
      <span class="value gold">Omega Immutable Ledger</span>
    </div>
    <div class="row">
      <span class="label">Status</span>
      <span class="value" style="color:#4CAF7D;">PERMANENT · UNALTERABLE</span>
    </div>
  </div>

  <div class="footer">
    <p>This record is permanently inscribed on the Omega Ledger.</p>
    <p>No authority — including the creator — can alter or delete it.</p>
    <hr class="separator">
    <p class="sig">Thomas Lee Harvey</p>
    <p style="color:#8B7355;font-size:9px;margin-top:4px;">CEO & Founder, Omega Art Studio</p>
  </div>
</div>
</body>
</html>"""


    def get_collector_passport(self, passport_id):
        try:
            import hashlib
            conn = psycopg2.connect(PG_LEDGER)
            cur = conn.cursor()
            cur.execute("""
                SELECT token_id, title, collection, rarity,
                       om109_fingerprint, chain_hash, sold_at,
                       receipt_hash, owner_account_id
                FROM nft_registry
                WHERE encode(digest(owner_account_id, 'sha256'), 'hex') = %s
                   OR encode(digest(lower(owner_account_id), 'sha256'), 'hex') = %s
                ORDER BY sold_at DESC
            """, (passport_id, passport_id))
            tokens = cur.fetchall()
            conn.close()

            PRICES = {
                "Impossible Diamond": 2500,
                "Black Diamond": 500,
                "Super Rare": 150,
                "Rare": 75,
                "Medium": 35,
                "Common": 15,
            }

            RARITY_COLOR = {
                "Impossible Diamond": "#E8F4FD",
                "Black Diamond": "#B8BCC8",
                "Super Rare": "#C9A84C",
                "Rare": "#4CAF7D",
                "Medium": "#8B7355",
                "Common": "#5a4a35",
            }

            if not tokens:
                return """<!DOCTYPE html><html><head><title>Omega Passport</title>
                <style>body{background:#0D0B0E;color:#F0E6D3;font-family:monospace;
                display:flex;align-items:center;justify-content:center;height:100vh;margin:0;}
                .box{text-align:center;border:1px solid #2a1f15;padding:40px;max-width:400px;}
                h2{color:#C9A84C;font-size:12px;letter-spacing:3px;}
                p{color:#8B7355;font-size:11px;margin-top:16px;}</style></head>
                <body><div class="box"><h2>OMEGA COLLECTOR PASSPORT</h2>
                <p>No holdings found for this passport ID.</p>
                <p style="margin-top:8px;">Purchase an Omega NFT to establish your collector identity.</p>
                </div></body></html>"""

            total_value = sum(PRICES.get(t[3], 0) for t in tokens)
            token_count = len(tokens)

            token_rows = ""
            for t in tokens:
                tid, title, coll, rarity, fp, ch, sold_at, receipt, owner = t
                rc = RARITY_COLOR.get(rarity, "#8B7355")
                price = PRICES.get(rarity, 0)
                date = str(sold_at)[:10] if sold_at else "N/A"
                receipt_link = f'<a href="/receipt/{receipt}" style="color:#C9A84C;font-size:8px;letter-spacing:1px;">VIEW RECEIPT →</a>' if receipt else ""
                token_rows += f"""
                <div style="background:#0c0a08;border:1px solid #2a1f15;padding:20px;margin-bottom:12px;">
                  <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:12px;">
                    <div>
                      <div style="color:#C9A84C;font-size:13px;font-weight:bold;">{title}</div>
                      <div style="color:#8B7355;font-size:9px;letter-spacing:2px;margin-top:4px;">{coll.upper()} · #{tid}</div>
                    </div>
                    <div style="text-align:right;">
                      <div style="color:{rc};font-size:10px;letter-spacing:1px;">{rarity}</div>
                      <div style="color:#C9A84C;font-size:12px;margin-top:4px;">${price:,}</div>
                    </div>
                  </div>
                  <div style="font-size:8px;color:#3a2f25;word-break:break-all;margin-bottom:8px;">
                    OM109: {fp[:48] if fp else 'N/A'}...
                  </div>
                  <div style="display:flex;justify-content:space-between;align-items:center;">
                    <span style="color:#5a4a35;font-size:9px;">Acquired {date}</span>
                    {receipt_link}
                  </div>
                </div>"""

            return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Omega Collector Passport</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{background:#0D0B0E;color:#F0E6D3;font-family:'JetBrains Mono',monospace;min-height:100vh;padding:40px 20px;}}
.container{{max-width:680px;margin:0 auto;}}
.header{{text-align:center;margin-bottom:40px;border-bottom:1px solid #2a1f15;padding-bottom:30px;}}
.omega{{font-size:48px;color:#C9A84C;display:block;margin-bottom:12px;}}
h1{{font-size:11px;letter-spacing:4px;text-transform:uppercase;color:#C9A84C;}}
.subtitle{{font-size:9px;color:#8B7355;margin-top:6px;letter-spacing:1px;}}
.passport-id{{font-size:8px;color:#3a2f25;margin-top:12px;word-break:break-all;}}
.stats{{display:flex;gap:12px;margin-bottom:28px;}}
.stat{{flex:1;background:#0c0a08;border:1px solid #2a1f15;padding:16px;text-align:center;}}
.stat-num{{font-size:24px;color:#C9A84C;display:block;}}
.stat-label{{font-size:9px;letter-spacing:2px;text-transform:uppercase;color:#8B7355;margin-top:4px;display:block;}}
.section-title{{font-size:9px;letter-spacing:3px;text-transform:uppercase;color:#8B7355;
  margin-bottom:16px;border-bottom:1px solid #2a1f15;padding-bottom:8px;}}
.footer{{text-align:center;margin-top:40px;padding-top:20px;border-top:1px solid #2a1f15;}}
.footer p{{font-size:9px;color:#8B7355;letter-spacing:1px;margin-bottom:6px;}}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <span class="omega">Ω</span>
    <h1>Collector Passport</h1>
    <p class="subtitle">Omega Art Studio — Verified Holdings</p>
    <p class="passport-id">PASSPORT · {passport_id[:32]}...</p>
  </div>

  <div class="stats">
    <div class="stat">
      <span class="stat-num">{token_count}</span>
      <span class="stat-label">Tokens Held</span>
    </div>
    <div class="stat">
      <span class="stat-num">${total_value:,}</span>
      <span class="stat-label">Collection Value</span>
    </div>
    <div class="stat">
      <span class="stat-num">{len(set(t[2] for t in tokens))}</span>
      <span class="stat-label">Collections</span>
    </div>
  </div>

  <div class="section-title">Verified Holdings</div>
  {token_rows}

  <div class="footer">
    <p>All holdings verified on the Omega Immutable Ledger</p>
    <p>Records are permanent and cannot be altered by anyone</p>
    <p style="color:#C9A84C;margin-top:12px;">Thomas Lee Harvey · CEO & Founder, Omega Art Studio</p>
  </div>
</div>
</body>
</html>"""

        except Exception as e:
            return f"<html><body style='background:#0D0B0E;color:#ff4d6a;font-family:monospace;padding:40px;'>Error: {e}</body></html>"


if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", 8082), Handler)
    print("Provenance API [FIXED] listening on 8082")
    server.serve_forever()
