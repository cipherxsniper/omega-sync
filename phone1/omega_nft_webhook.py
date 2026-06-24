import os, hashlib, datetime, smtplib, random
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

QUOTES = [
    "The clock melts because time was never solid.",
    "Every door opens onto a room that was already inside you.",
    "The mirror remembers what the eye forgot.",
    "To own a dream is to hold water in a fist of light.",
    "The archive does not sleep. It waits.",
    "Your signature is the ghost of a hand that moved through fire.",
    "Infinity is not large. It is simply unwilling to stop.",
]

def _quote():
    return random.choice(QUOTES)

COLL_DIR = {
    "echoes":   "echoes_of_eternity",
    "somnium":  "somnium",
    "paracosm": "paracosm",
    "monolith": "monolith",
}

RARITY_LABEL = {
    "impossible_diamond": "Impossible Diamond",
    "black_diamond":      "Black Diamond",
    "super_rare":         "Super Rare",
    "rare":               "Rare",
    "medium":             "Medium",
    "common":             "Common",
}

GENESIS = {
    "echoes":   "OMEGA_GENESIS_THOMAS_LEE_HARVEY_OM109_2024",
    "somnium":  "OMEGA_GENESIS_THOMAS_LEE_HARVEY_SOMNIUM_2026",
    "paracosm": "OMEGA_GENESIS_THOMAS_LEE_HARVEY_PARACOSM_2026",
    "monolith": "OMEGA_GENESIS_THOMAS_LEE_HARVEY_OM109_2024_MONOLITH",
}

def _pg():
    import psycopg2, psycopg2.extras
    return psycopg2.connect(
        host="127.0.0.1", port=5432, dbname="omega_ledger",
        user="postgres",
        cursor_factory=psycopg2.extras.RealDictCursor
    )

def _live_verify_url(collection, token_id):
    """Fetch current tunnel URL from broker at send time."""
    try:
        import urllib.request
        r = urllib.request.urlopen('http://127.0.0.1:8085/current-api', timeout=3)
        import json
        data = json.loads(r.read())
        base = data.get('api', '').rstrip('/')
        if base:
            return f"{base}/nft/verify/{collection}/{token_id}"
    except:
        pass
    return f"http://127.0.0.1:8082/nft/verify/{collection}/{token_id}"


def _live_receipt_url(receipt_hash):
    """Fetch current tunnel URL and build receipt verification link."""
    try:
        import urllib.request, json
        r = urllib.request.urlopen('http://127.0.0.1:8085/current-api', timeout=3)
        data = json.loads(r.read())
        base = data.get('api', '').rstrip('/')
        if base:
            return f"{base}/receipt/{receipt_hash}"
    except:
        pass
    return f"http://127.0.0.1:8082/receipt/{receipt_hash}"

def _live_passport_url(buyer_email):
    """Generate passport URL from buyer email hash."""
    import hashlib
    passport_id = hashlib.sha256(buyer_email.lower().encode()).hexdigest()
    try:
        import urllib.request, json
        r = urllib.request.urlopen('http://127.0.0.1:8085/current-api', timeout=3)
        data = json.loads(r.read())
        base = data.get('api', '').rstrip('/')
        if base:
            return f"{base}/collector/{passport_id}"
    except:
        pass
    return f"http://127.0.0.1:8082/collector/{passport_id}"

def _image_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def _om109(collection, token_id, image_hash):
    seed = GENESIS[collection]
    genesis = hashlib.sha256(seed.encode()).hexdigest()
    sig_a = hashlib.sha256(f"{genesis}:A:{token_id}:{image_hash}".encode()).hexdigest()
    sig_b = hashlib.sha256(f"{genesis}:B:{token_id}:{image_hash}:{sig_a}".encode()).hexdigest()
    fp = hashlib.sha256((sig_a[:32] + sig_b[:32]).encode()).hexdigest()
    return {"sig_a": sig_a, "sig_b": sig_b, "fingerprint": fp}

def _write_ledger(conn, token, buyer, session_id):
    idem = hashlib.sha256(
        f"NFT_SALE:{token["collection"]}:{token["token_id"]}:{session_id}".encode()
    ).hexdigest()[:32]
    conn.execute("""
        INSERT INTO ledger_entries
            (idempotency_key, event_type, collection, token_id,
             from_account, to_account, amount_usd, stripe_session_id,
             om109_fingerprint, created_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
        ON CONFLICT (idempotency_key) DO NOTHING
    """, (idem, "NFT_SALE", token["collection"], token["token_id"],
           "OMEGA_ART_STUDIO", buyer, token.get("price_usd", 0),
           session_id, token.get("om109_fingerprint", "")))

def _send_coa_email(token, buyer, image_path, receipt_hash="", passport_url=""):
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    if not smtp_user or not smtp_pass:
        print("[nft_webhook] SMTP not configured")
        return False
    rarity = RARITY_LABEL.get(token.get("rarity","common"), token.get("rarity",""))
    tid = token["token_id"]
    coll = token["collection"].replace("_"," ").title()
    title = token.get("title", f"Token #{tid}")
    fp = token.get("om109_fingerprint", "")
    ch = token.get("chain_hash", "")
    ts = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    quote = _quote()
    body = f"""\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\nCERTIFICATE OF AUTHENTICITY\nOmega Art Studio\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\nTitle      : {title}\nCollection : {coll}\nToken ID   : {tid}\nRarity     : {rarity}\nOM109      : {fp}\nChain Hash : {ch}\nRecorded   : {ts}\n\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\nCUSTODIAL NOTICE\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\nThis is a digital asset. The PNG, this certificate,\nand the OM109 fingerprint are your responsibility.\nOmega provides the provenance. You hold the asset.\n\nVerify: {_live_verify_url(token["collection"], tid)}\n\n"{quote}"\n\nThomas Lee Harvey\nCEO & Founder, Omega Art Studio\n"""

    msg = MIMEMultipart()
    msg["From"] = smtp_user
    msg["To"] = buyer
    msg["Subject"] = f"Your {rarity} — {title} | Certificate of Authenticity"
    msg.attach(MIMEText(body, "plain"))
    if image_path and os.path.exists(image_path):
        with open(image_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="{token["collection"]}_{tid}.png"')
        msg.attach(part)
    try:
        with smtplib.SMTP(smtp_host, smtp_port) as s:
            s.starttls()
            s.login(smtp_user, smtp_pass)
            s.sendmail(smtp_user, buyer, msg.as_string())
        print(f"[nft_webhook] COA emailed to {buyer}")
        return True
    except Exception as e:
        print(f"[nft_webhook] Email failed: {e}")
        return False

def handle_nft_checkout(data):
    price_id = ""
    items = data.get("line_items", {}).get("data", [])
    if items:
        price_id = items[0].get("price", {}).get("id", "")
    if not price_id:
        return False
    conn = _pg()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM nft_registry WHERE stripe_price_id = %s", (price_id,))
        token = cur.fetchone()
        if not token:
            conn.close()
            return False
        token = dict(token)
        coll = token["collection"]
        tid = token["token_id"]
        buyer = data.get("customer_email") or data.get("customer_details", {}).get("email", "unknown")
        session_id = data.get("id", "")
        coll_dir = COLL_DIR.get(coll, coll)
        image_path = os.path.expanduser(f"~/{coll_dir}/images/{tid}.png")
        cur.execute("UPDATE nft_registry SET sale_status=%s, owner_account_id=%s, sold_at=NOW() WHERE collection=%s AND token_id=%s AND sale_status!=%s",
            ("sold", buyer, coll, tid, "sold"))
        _write_ledger(conn, token, buyer, session_id)
        conn.commit()
        if buyer != "unknown":
            _send_coa_email(token, buyer, image_path, receipt_hash, passport_url)
        print(f"[nft_webhook] Sale complete: {coll}/{tid} -> {buyer}")
        conn.close()
        return True
    except Exception as e:
        conn.rollback()
        conn.close()
        print(f"[nft_webhook] ERROR: {e}")
        return False
