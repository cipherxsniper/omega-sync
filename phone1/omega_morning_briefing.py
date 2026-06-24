#!/usr/bin/env python3
import os
import json
import psycopg2
import subprocess
import sys
from datetime import datetime, timedelta

PG_BANK = "dbname=omega_bank user=postgres host=127.0.0.1 port=5432"
PG_LEDGER = "dbname=omega_ledger user=postgres host=127.0.0.1 port=5432"

def get_oracle_score():
    """Get current Oracle grade from v3"""
    try:
        result = subprocess.run(['python3', '/home/omega/omega_oracle_v3.py'], 
                              capture_output=True, text=True, timeout=15)
        output = result.stdout + result.stderr
        for line in output.split('\n'):
            if 'Grade:' in line:
                grade = line.split('Grade:')[1].strip().split()[0]
                return grade
        return 'N/A'
    except Exception as e:
        print(f"[DEBUG] Oracle error: {str(e)}", file=sys.stderr)
        return 'N/A'

def get_nft_sales_overnight():
    """Get NFT sales in last 24 hours"""
    try:
        conn = psycopg2.connect(PG_LEDGER)
        cur = conn.cursor()
        cur.execute("""
            SELECT COUNT(*) as sold_count, SUM(price_usd) as total_revenue
            FROM nft_registry
            WHERE sold_at >= NOW() - INTERVAL '24 hours'
            AND sale_status = 'sold'
        """)
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row and row[0]:
            return {'count': row[0], 'revenue': float(row[1] or 0)}
        return {'count': 0, 'revenue': 0.0}
    except Exception as e:
        return {'count': 0, 'revenue': 0.0}

def get_wallet_balances():
    """Get total wallet balances"""
    try:
        conn = psycopg2.connect(PG_BANK)
        cur = conn.cursor()
        cur.execute("SELECT SUM(available_balance) FROM wallets")
        total = float(cur.fetchone()[0] or 0)
        cur.execute("SELECT COUNT(*) FROM wallets")
        count = cur.fetchone()[0]
        cur.close()
        conn.close()
        return {'total': total, 'count': count}
    except Exception as e:
        return {'total': 0, 'count': 0}

def get_system_health():
    """Check critical processes"""
    health = {}
    processes = [
        ('Oracle', 'omega_v10.py'),
        ('Sentinel', 'omega_sentinel.py'),
        ('Provenance API', 'omega_provenance_api.py'),
        ('Gallery Server', 'omega_gallery_server.py'),
    ]
    for name, pattern in processes:
        result = subprocess.run(['pgrep', '-f', pattern], capture_output=True)
        health[name] = 'UP' if result.returncode == 0 else 'DOWN'
    return health

def get_tunnel_urls():
    """Get current tunnel URLs from broker"""
    try:
        result = subprocess.run(['curl', '-s', 'http://127.0.0.1:8085/current-all'],
                              capture_output=True, text=True, timeout=5)
        data = json.loads(result.stdout)
        return data
    except:
        return {'error': 'Broker unavailable'}

def format_telegram_message(oracle, sales, wallets, health, tunnels):
    """Format morning briefing for Telegram"""
    msg = "☀️ <b>OMEGA MORNING BRIEFING</b>\n\n"
    
    msg += f"<b>Oracle Grade:</b> {oracle}\n"
    msg += f"<b>NFT Sales (24h):</b> {sales.get('count', 0)} sold, ${sales.get('revenue', 0):,.2f}\n"
    msg += f"<b>Wallet Total:</b> ${wallets.get('total', 0):,.2f} ({wallets.get('count', 0)} wallets)\n\n"
    
    msg += "<b>System Health:</b>\n"
    for name, status in health.items():
        icon = "✅" if status == "UP" else "❌"
        msg += f"  {icon} {name}: {status}\n"
    
    msg += "\n<b>Public URLs:</b>\n"
    if 'error' in tunnels:
        msg += f"  ⚠️ {tunnels['error']}\n"
    else:
        if 'gallery' in tunnels:
            msg += f"  🎨 Gallery: {tunnels['gallery']}\n"
        if 'api' in tunnels:
            msg += f"  ⚙️ API: {tunnels['api']}\n"
    
    msg += f"\n<i>Generated {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>"
    return msg

def send_telegram(message):
    """Send message via Telegram bot"""
    env_file = os.path.expanduser('~/.env')
    token = None
    chat_id = None
    
    try:
        with open(env_file) as f:
            for line in f:
                if line.startswith('TELEGRAM_BOT_TOKEN='):
                    token = line.split('=', 1)[1].strip()
                elif line.startswith('TELEGRAM_CHAT_ID='):
                    chat_id = line.split('=', 1)[1].strip()
    except:
        return False
    
    if not token or not chat_id:
        return False
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': 'HTML'
    }
    
    try:
        result = subprocess.run(['curl', '-s', '-X', 'POST', url, 
                               '-H', 'Content-Type: application/json',
                               '-d', json.dumps(payload)],
                              capture_output=True, text=True, timeout=10)
        response = json.loads(result.stdout)
        return response.get('ok', False)
    except:
        return False

def install_cron():
    """Install 8am daily cron job"""
    cron_cmd = "0 8 * * * python3 /data/data/com.termux/files/home/omega_morning_briefing.py"
    try:
        result = subprocess.run(['crontab', '-l'], capture_output=True, text=True)
        existing = result.stdout
        
        if 'omega_morning_briefing.py' not in existing:
            new_cron = existing + cron_cmd + "\n"
            subprocess.run(['crontab'], input=new_cron, text=True)
            return True
        return True
    except:
        return False

def main():
    if '--install' in sys.argv:
        print("[*] Installing 8am daily briefing...")
        if install_cron():
            print("[✓] Cron job installed")
        else:
            print("[ERROR] Cron install failed")
        return
    
    oracle = get_oracle_score()
    sales = get_nft_sales_overnight()
    wallets = get_wallet_balances()
    health = get_system_health()
    tunnels = get_tunnel_urls()
    
    message = format_telegram_message(oracle, sales, wallets, health, tunnels)
    if send_telegram(message):
        print("[✓] Briefing sent")
    else:
        print("[ERROR] Briefing failed")

if __name__ == "__main__":
    main()
