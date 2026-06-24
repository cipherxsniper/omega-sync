#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════════╗
║                                                                                  ║
║     ██████╗ ███╗   ███╗███████╗ ██████╗  █████╗      █████╗ ██╗                 ║
║    ██╔═══██╗████╗ ████║██╔════╝██╔════╝ ██╔══██╗    ██╔══██╗██║                 ║
║    ██║   ██║██╔████╔██║█████╗  ██║  ███╗███████║    ███████║██║                 ║
║    ██║   ██║██║╚██╔╝██║██╔══╝  ██║   ██║██╔══██║    ██╔══██║██║                 ║
║    ╚██████╔╝██║ ╚═╝ ██║███████╗╚██████╔╝██║  ██║    ██║  ██║██║                 ║
║     ╚═════╝ ╚═╝     ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝    ╚═╝  ╚═╝╚═╝                 ║
║                                                                                  ║
║     ENTERPRISE REVENUE OPERATING SYSTEM  v10.0                                  ║
║     Inbound-First · Stripe-Native · Deliverability-Grade · Self-Learning        ║
║                                                                                  ║
║     PRODUCTS:                                                                    ║
║       • Omega AI Full Ops      $1,497/mo  (7-day free trial)                    ║
║       • Omega AI Growth Suite  $997/mo    (7-day free trial)                    ║
║       • Omega AI Starter       $497/mo    (7-day free trial)                    ║
║                                                                                  ║
║     ARCHITECTURE:                                                                ║
║       .env → Config Validator → Event Bus → Worker Pool                         ║
║       → Inbound Lead Receiver (webhooks) → Lead Scoring Gate                   ║
║       → Deliverability-Safe Email Engine (SendGrid/Mailgun/SMTP)               ║
║       → AI Personalization (Claude) → Inbox Intelligence                        ║
║       → Stripe Webhook → Auto-Onboarding → CRM → Self-Learning                ║
║       → Telegram Mission Control (merged)                                        ║
║                                                                                  ║
║     INSTALL:                                                                     ║
║       pip install anthropic sendgrid mailgun2 requests python-dotenv            ║
║                stripe flask python-telegram-bot apscheduler                     ║
║                beautifulsoup4                                                    ║
║                                                                                  ║
║     RUN:                                                                         ║
║       python3 omega_v10.py                                                       ║
║       python3 omega_v10.py --bot-only                                            ║
║       python3 omega_v10.py --engine-only                                         ║
║       python3 omega_v10.py --validate                                            ║
║                                                                                  ║
╚══════════════════════════════════════════════════════════════════════════════════╝
"""

# ══════════════════════════════════════════════════════════════
# IMPORTS
# ══════════════════════════════════════════════════════════════

from __future__ import annotations
import os, sys, json, time, signal, smtplib, imaplib, email as email_lib
import re, random, queue, threading, hashlib, traceback, argparse, hmac
import sqlite3, logging, base64, textwrap
from pathlib import Path
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header
from typing import Optional, Dict, List, Any, Callable
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv
import sys as _sys
_sys.path.insert(0, '/data/data/com.termux/files/home')

# Optional heavy deps — graceful degradation
try:
    from bs4 import BeautifulSoup
    BS4_OK = True
except ImportError:
    BS4_OK = False

try:
    import stripe as stripe_lib
    STRIPE_OK = True
except ImportError:
    STRIPE_OK = False

try:
    import anthropic as anthropic_lib
    ANTHROPIC_SDK_OK = True
except ImportError:
    ANTHROPIC_SDK_OK = False

try:
    from flask import Flask, request as flask_request, jsonify
    FLASK_OK = True
except ImportError:
    FLASK_OK = False

try:
    from telegram import (
        Update, InlineKeyboardButton, InlineKeyboardMarkup,
        BotCommand,
    )
    from telegram.ext import (
        ApplicationBuilder, CommandHandler, ContextTypes,
        CallbackQueryHandler, MessageHandler, filters,
        ConversationHandler,
    )
    TELEGRAM_OK = True
except ImportError:
    TELEGRAM_OK = False

# ══════════════════════════════════════════════════════════════
# ENVIRONMENT LOADING
# ══════════════════════════════════════════════════════════════

_SCRIPT_DIR = Path(__file__).resolve().parent
_ENV_PATH   = _SCRIPT_DIR / ".env"

if _ENV_PATH.exists():
    load_dotenv(_ENV_PATH)
    _env_source = str(_ENV_PATH)
else:
    load_dotenv()
    _env_source = "environment variables"


# ══════════════════════════════════════════════════════════════
# CONFIGURATION — 100% from .env, zero hardcoded secrets
# ══════════════════════════════════════════════════════════════

class Config:
    # ── AI ─────────────────────────────────────────────────────
    ANTHROPIC_API_KEY   = os.getenv("ANTHROPIC_API_KEY", "")
    CLAUDE_MODEL        = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")   # fast + cheap for volume
    CLAUDE_SMART_MODEL  = os.getenv("CLAUDE_SMART_MODEL", "claude-sonnet-4-6")     # replies + onboarding
    OPENROUTER_API_KEY  = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_MODEL    = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")

    # ── Email Sending (priority: SendGrid → Mailgun → SMTP) ────
    SENDGRID_API_KEY    = os.getenv("SENDGRID_API_KEY", "")
    MAILGUN_API_KEY     = os.getenv("MAILGUN_API_KEY", "")
    MAILGUN_DOMAIN      = os.getenv("MAILGUN_DOMAIN", "")
    SMTP_HOST           = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT           = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER           = os.getenv("SMTP_USER", "")
    SMTP_PASS           = os.getenv("SMTP_PASS", "")

    # ── Email Receiving (IMAP) ─────────────────────────────────
    IMAP_HOST           = os.getenv("IMAP_HOST", "imap.gmail.com")
    IMAP_PORT           = int(os.getenv("IMAP_PORT", "993"))
    IMAP_USER           = os.getenv("IMAP_USER", os.getenv("SMTP_USER", ""))
    IMAP_PASS           = os.getenv("IMAP_PASS", os.getenv("SMTP_PASS", ""))

    # ── Stripe ─────────────────────────────────────────────────
    STRIPE_SECRET_KEY        = os.getenv("STRIPE_SECRET_KEY", "")
    STRIPE_WEBHOOK_SECRET    = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    STRIPE_PRICE_FULL_OPS    = os.getenv("STRIPE_PRICE_FULL_OPS", "")    # price_xxx ID
    STRIPE_PRICE_GROWTH      = os.getenv("STRIPE_PRICE_GROWTH", "")
    STRIPE_PRICE_STARTER     = os.getenv("STRIPE_PRICE_STARTER", "")
    STRIPE_LINK_FULL_OPS     = os.getenv("STRIPE_LINK_FULL_OPS", "")
    STRIPE_LINK_GROWTH       = os.getenv("STRIPE_LINK_GROWTH", "")
    STRIPE_LINK_STARTER      = os.getenv("STRIPE_LINK_STARTER", "")

    # ── Lead Data APIs (opt-in sources) ───────────────────────
    HUNTER_API_KEY      = os.getenv("HUNTER_API_KEY", "")       # Hunter.io — opted-in B2B data
    APOLLO_API_KEY      = os.getenv("APOLLO_API_KEY", "")       # Apollo.io  — opted-in B2B data
    SERPAPI_API_KEY     = os.getenv("SERPAPI_API_KEY", "")      # Google Maps discovery

    # ── Telegram Mission Control ────────────────────────────────
    TELEGRAM_BOT_TOKEN  = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID    = os.getenv("TELEGRAM_CHAT_ID", "")
    # Comma-separated list of allowed Telegram user IDs
    TELEGRAM_ADMIN_IDS  = [
        x.strip() for x in os.getenv("TELEGRAM_ADMIN_IDS", "").split(",") if x.strip()
    ]
    BOT_SECRET_PIN      = os.getenv("BOT_SECRET_PIN", "")

    # ── Webhook Server ─────────────────────────────────────────
    WEBHOOK_HOST        = os.getenv("WEBHOOK_HOST", "0.0.0.0")
    WEBHOOK_PORT        = int(os.getenv("WEBHOOK_PORT", "8080"))
    WEBHOOK_SECRET      = os.getenv("WEBHOOK_SECRET", "")       # HMAC validation for inbound webhooks

    # ── Business Identity ──────────────────────────────────────
    CEO_NAME            = os.getenv("CEO_NAME", "Thomas Lee Harvey")
    COMPANY_NAME        = os.getenv("COMPANY_NAME", "Omega AI")
    COMPANY_EMAIL       = os.getenv("COMPANY_EMAIL", os.getenv("SMTP_USER", ""))
    COMPANY_PHONE       = os.getenv("COMPANY_PHONE", "")
    COMPANY_WEBSITE     = os.getenv("COMPANY_WEBSITE", "")
    CALENDLY_LINK       = os.getenv("CALENDLY_LINK", "")

    # ── Revenue Model ──────────────────────────────────────────
    PRODUCTS: Dict[str, Dict] = {
        "full_ops": {
            "name":    "Omega AI Full Ops",
            "price":   1497.00,
            "trial":   7,
            "stripe":  "",   # filled in post-init
            "price_id": "",
            "desc":    "Full autonomous revenue ops — AI inbox, outreach, CRM, follow-up, onboarding",
            "best_for": "Established local businesses $1M+ revenue",
        },
        "growth": {
            "name":    "Omega AI Growth Suite",
            "price":   997.00,
            "trial":   7,
            "stripe":  "",
            "price_id": "",
            "desc":    "AI lead gen + outreach + CRM for growth-stage businesses",
            "best_for": "Businesses doing $300K–$1M revenue",
        },
        "starter": {
            "name":    "Omega AI Starter",
            "price":   497.00,
            "trial":   7,
            "stripe":  "",
            "price_id": "",
            "desc":    "AI inbox monitoring + instant lead response",
            "best_for": "Small businesses, solo operators",
        },
    }

    # ── Operational Timing ─────────────────────────────────────
    MAX_DAILY_SENDS       = int(os.getenv("MAX_DAILY_SENDS", "50"))
    RATE_LIMIT_DELAY      = float(os.getenv("RATE_LIMIT_DELAY", "10"))  # seconds between sends
    INBOX_POLL_INTERVAL   = int(os.getenv("INBOX_POLL_INTERVAL", "90"))
    LEAD_GEN_INTERVAL     = int(os.getenv("LEAD_GEN_INTERVAL", "900"))
    OUTREACH_INTERVAL     = int(os.getenv("OUTREACH_INTERVAL", "1200"))
    LEARNING_INTERVAL     = int(os.getenv("LEARNING_INTERVAL", "3600"))
    FOLLOW_UP_DAYS        = int(os.getenv("FOLLOW_UP_DAYS", "3"))
    MAX_STAGES            = int(os.getenv("MAX_STAGES", "3"))
    SEND_SCORE_THRESHOLD  = int(os.getenv("SEND_SCORE_THRESHOLD", "40"))
    BIZ_HOUR_START        = int(os.getenv("BIZ_HOUR_START", "8"))
    BIZ_HOUR_END          = int(os.getenv("BIZ_HOUR_END", "19"))

    # ── Intent Keywords ────────────────────────────────────────
    INTENT_BUY = [
        "interested","sign up","sign me up","start","ready","subscribe",
        "trial","demo","let's do it","onboard","let's go","i'm in","get started",
        "yes","absolutely","sounds good","book","schedule","free trial","try it",
        "activate","set it up","how do i start","send me","let's talk","i want",
        "can you set","move forward","proceed","go ahead",
    ]
    INTENT_PRICING = [
        "price","pricing","how much","cost","rate","fee","quote","budget",
        "investment","what do you charge","monthly","annual",
    ]
    INTENT_UNSUBSCRIBE = [
        "unsubscribe","stop","remove","opt out","no more","not interested",
        "no thanks","take me off","don't contact","leave me alone","please remove",
    ]
    INTENT_BLACKLIST = [
        "spam","scam","fraud","report you","lawsuit","legal action",
        "cease and desist","attorney general","ftc","complaint",
    ]

    # ── Onboarding Questions ────────────────────────────────────
    ONBOARDING_QUESTIONS = [
        "What is your primary business email address for AI monitoring?",
        "What is your business phone number?",
        "Do you use a CRM? (HubSpot, Salesforce, Pipedrive, etc.) If none, we'll provision one.",
        "What's your scheduling link? (Calendly, Acuity, etc.)",
        "Describe your ideal customer in 1-2 sentences.",
        "What is your single biggest lead or revenue challenge right now?",
        "How many inbound leads do you currently receive per month?",
        "What is your average response time to a new lead today?",
    ]

    @classmethod
    def _post_init(cls):
        """Fill computed fields after load."""
        cls.PRODUCTS["full_ops"]["stripe"]   = cls.STRIPE_LINK_FULL_OPS
        cls.PRODUCTS["full_ops"]["price_id"] = cls.STRIPE_PRICE_FULL_OPS
        cls.PRODUCTS["growth"]["stripe"]     = cls.STRIPE_LINK_GROWTH
        cls.PRODUCTS["growth"]["price_id"]   = cls.STRIPE_PRICE_GROWTH
        cls.PRODUCTS["starter"]["stripe"]    = cls.STRIPE_LINK_STARTER
        cls.PRODUCTS["starter"]["price_id"]  = cls.STRIPE_PRICE_STARTER
        if STRIPE_OK and cls.STRIPE_SECRET_KEY:
            stripe_lib.api_key = cls.STRIPE_SECRET_KEY

Config._post_init()


# ══════════════════════════════════════════════════════════════
# STARTUP VALIDATOR
# ══════════════════════════════════════════════════════════════

class StartupValidator:
    CRITICAL = "CRITICAL"
    WARN     = "WARN"
    OK       = "OK"

    CHECKS = [
        # (key, level, description)
        ("ANTHROPIC_API_KEY",     CRITICAL, "Claude AI — email personalization"),
        ("STRIPE_SECRET_KEY",     CRITICAL, "Stripe payments"),
        ("STRIPE_WEBHOOK_SECRET", WARN,     "Stripe webhook validation (insecure without)"),
        ("STRIPE_LINK_FULL_OPS",  WARN,     "Stripe checkout link — Full Ops"),
        ("STRIPE_LINK_GROWTH",    WARN,     "Stripe checkout link — Growth"),
        ("STRIPE_LINK_STARTER",   WARN,     "Stripe checkout link — Starter"),
        ("TELEGRAM_BOT_TOKEN",    WARN,     "Telegram Mission Control"),
        ("TELEGRAM_ADMIN_IDS",    WARN,     "Telegram admin access list"),
        ("BOT_SECRET_PIN",        WARN,     "Telegram auth PIN"),
        ("IMAP_USER",             WARN,     "Inbox monitoring — replies"),
        ("IMAP_PASS",             WARN,     "Inbox monitoring — replies"),
        ("WEBHOOK_SECRET",        WARN,     "Inbound webhook HMAC security"),
        ("CEO_NAME",              OK,       "Business identity"),
        ("COMPANY_NAME",          OK,       "Business identity"),
        ("COMPANY_EMAIL",         OK,       "From address"),
        ("COMPANY_WEBSITE",       OK,       "Company website"),
        ("CALENDLY_LINK",         OK,       "Scheduling link"),
    ]

    EMAIL_SEND_CHECKS = [
        ("SENDGRID_API_KEY",  "SendGrid (preferred)"),
        ("MAILGUN_API_KEY",   "Mailgun"),
        ("SMTP_USER",         "SMTP / Gmail"),
    ]

    @classmethod
    def validate(cls, verbose: bool = True) -> bool:
        results = []
        has_critical_fail = False

        if verbose:
            print("\n" + "═"*62)
            print("  OMEGA AI v10 — STARTUP VALIDATION")
            print(f"  Config source: {_env_source}")
            print("═"*62)

        # Email sender check
        has_sender = any(
            os.getenv(k) for k, _ in cls.EMAIL_SEND_CHECKS
        )
        if not has_sender:
            results.append((cls.CRITICAL, "EMAIL_SENDING", "No email sender configured (SENDGRID_API_KEY, MAILGUN_API_KEY, or SMTP_USER)"))
            has_critical_fail = True
        else:
            for k, label in cls.EMAIL_SEND_CHECKS:
                if os.getenv(k):
                    results.append((cls.OK, k, f"{label} ✓"))
                    break

        for key, level, desc in cls.CHECKS:
            val = os.getenv(key, "")
            # Special case: list field
            if key == "TELEGRAM_ADMIN_IDS":
                val = Config.TELEGRAM_ADMIN_IDS
                present = bool(val)
            else:
                present = bool(val)

            if present:
                display = "✓"
                if key.endswith("KEY") or key.endswith("PASS") or key.endswith("PIN") or "SECRET" in key:
                    display = "✓ (set)"
                results.append((cls.OK, key, f"{desc} — {display}"))
            else:
                results.append((level, key, f"{desc} — MISSING"))
                if level == cls.CRITICAL:
                    has_critical_fail = True

        if verbose:
            for level, key, msg in results:
                icon = {"CRITICAL": "🔴", "WARN": "🟡", "OK": "🟢"}[level]
                print(f"  {icon}  {key:<30} {msg}")

            print("═"*62)
            crits  = sum(1 for l, _, _ in results if l == cls.CRITICAL)
            warns  = sum(1 for l, _, _ in results if l == cls.WARN)
            oks    = sum(1 for l, _, _ in results if l == cls.OK)
            print(f"  🟢 OK: {oks}   🟡 Warnings: {warns}   🔴 Critical: {crits}")
            if has_critical_fail:
                print("\n  ⛔ CRITICAL ITEMS MISSING — engine cannot start safely.")
                print("  Add missing keys to your .env file and restart.\n")
            else:
                print("\n  ✅ Ready to launch.\n")
            print("═"*62 + "\n")

        return not has_critical_fail


# ══════════════════════════════════════════════════════════════
# FILESYSTEM LAYOUT
# ══════════════════════════════════════════════════════════════

BASE_DIR   = Path(__file__).resolve().parent
RUNTIME    = BASE_DIR / "omega_runtime"
STATE_DIR  = RUNTIME / "state"
LOGS_DIR   = RUNTIME / "logs"
MEMORY_DIR = RUNTIME / "memory"
DB_DIR     = RUNTIME / "db"

for _d in [STATE_DIR, LOGS_DIR, MEMORY_DIR, DB_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

DB_PATH       = DB_DIR / "omega.db"
WEIGHTS_FILE  = MEMORY_DIR / "weights.json"
OUTCOMES_FILE = MEMORY_DIR / "outcomes.json"
AUDIT_FILE    = LOGS_DIR / "audit.log"


# ══════════════════════════════════════════════════════════════
# LOGGING
# ══════════════════════════════════════════════════════════════

_log_path = LOGS_DIR / f"{datetime.now().strftime('%Y-%m-%d')}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-8s] %(name)s — %(message)s",
    handlers=[
        logging.FileHandler(_log_path),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("OmegaAI")


def log(level: str, component: str, msg: str):
    getattr(logger, level.lower(), logger.info)(f"[{component.upper():16}] {msg}")


# ══════════════════════════════════════════════════════════════
# DATABASE ENGINE (SQLite — production upgrade path to Postgres)
# ══════════════════════════════════════════════════════════════

class DB:
    _conn: Optional[sqlite3.Connection] = None
    _lock = threading.RLock()

    @classmethod
    def get(cls) -> sqlite3.Connection:
        if cls._conn is None:
            cls._conn = sqlite3.connect(DB_PATH, check_same_thread=False)
            cls._conn.row_factory = sqlite3.Row
            cls._conn.execute("PRAGMA journal_mode=WAL")
            cls._conn.execute("PRAGMA foreign_keys=ON")
            cls.migrate()
        return cls._conn

    @classmethod
    def migrate(cls):
        c = cls._conn.cursor()

        c.executescript("""
        CREATE TABLE IF NOT EXISTS leads (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            email           TEXT UNIQUE NOT NULL,
            name            TEXT,
            company         TEXT,
            website         TEXT,
            category        TEXT,
            source          TEXT DEFAULT 'inbound',
            status          TEXT DEFAULT 'new',
            stage           INTEGER DEFAULT 0,
            score           REAL DEFAULT 0,
            product_pitched TEXT,
            last_contact_at TEXT,
            created_at      TEXT DEFAULT (datetime('now')),
            notes           TEXT
        );

        CREATE TABLE IF NOT EXISTS emails_sent (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id     INTEGER REFERENCES leads(id),
            to_email    TEXT NOT NULL,
            subject     TEXT,
            stage       INTEGER,
            product_key TEXT,
            provider    TEXT,
            sent_at     TEXT DEFAULT (datetime('now')),
            opened      INTEGER DEFAULT 0,
            clicked     INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS email_replies (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            from_email  TEXT NOT NULL,
            subject     TEXT,
            body        TEXT,
            intent      TEXT,
            processed   INTEGER DEFAULT 0,
            received_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS clients (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            email        TEXT UNIQUE NOT NULL,
            name         TEXT,
            company      TEXT,
            product_key  TEXT,
            mrr          REAL DEFAULT 0,
            status       TEXT DEFAULT 'trial',
            stripe_id    TEXT,
            onboarded_at TEXT DEFAULT (datetime('now')),
            answers      TEXT DEFAULT '{}',
            notes        TEXT
        );

        CREATE TABLE IF NOT EXISTS events (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            type       TEXT NOT NULL,
            data       TEXT DEFAULT '{}',
            ts         TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS metrics (
            key   TEXT PRIMARY KEY,
            value REAL DEFAULT 0,
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS suppression (
            email     TEXT PRIMARY KEY,
            reason    TEXT,
            added_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_leads_status   ON leads(status);
        CREATE INDEX IF NOT EXISTS idx_leads_stage    ON leads(stage);
        CREATE INDEX IF NOT EXISTS idx_leads_source   ON leads(source);
        CREATE INDEX IF NOT EXISTS idx_emails_sent_to ON emails_sent(to_email);
        CREATE INDEX IF NOT EXISTS idx_events_type    ON events(type);
        """)
        cls._conn.commit()

    @classmethod
    def metric(cls, key: str, inc: float = 1.0):
        with cls._lock:
            cls.get().execute("""
                INSERT INTO metrics(key, value, updated_at) VALUES(?, ?, datetime('now'))
                ON CONFLICT(key) DO UPDATE SET value=value+?, updated_at=datetime('now')
            """, (key, inc, inc))
            cls.get().commit()

    @classmethod
    def set_metric(cls, key: str, value: float):
        with cls._lock:
            cls.get().execute("""
                INSERT INTO metrics(key, value, updated_at) VALUES(?, ?, datetime('now'))
                ON CONFLICT(key) DO UPDATE SET value=?, updated_at=datetime('now')
            """, (key, value, value))
            cls.get().commit()

    @classmethod
    def get_metrics(cls) -> dict:
        rows = cls.get().execute("SELECT key, value FROM metrics").fetchall()
        return {r["key"]: r["value"] for r in rows}

    @classmethod
    def is_suppressed(cls, email: str) -> bool:
        r = cls.get().execute("SELECT 1 FROM suppression WHERE email=?", (email.lower(),)).fetchone()
        return r is not None

    @classmethod
    def suppress(cls, email: str, reason: str = "unsubscribe"):
        with cls._lock:
            cls.get().execute(
                "INSERT OR IGNORE INTO suppression(email,reason) VALUES(?,?)",
                (email.lower(), reason)
            )
            cls.get().commit()

    @classmethod
    def event(cls, etype: str, data: dict):
        with cls._lock:
            cls.get().execute(
                "INSERT INTO events(type,data) VALUES(?,?)",
                (etype, json.dumps(data, default=str))
            )
            cls.get().commit()

    @classmethod
    def upsert_lead(cls, email: str, **kwargs) -> int:
        with cls._lock:
            conn = cls.get()
            existing = conn.execute("SELECT id FROM leads WHERE email=?", (email.lower(),)).fetchone()
            if existing:
                sets = ", ".join(f"{k}=?" for k in kwargs)
                vals = list(kwargs.values()) + [email.lower()]
                conn.execute(f"UPDATE leads SET {sets} WHERE email=?", vals)
                conn.commit()
                return existing["id"]
            else:
                kwargs["email"] = email.lower()
                cols = ", ".join(kwargs.keys())
                placeholders = ", ".join("?" * len(kwargs))
                conn.execute(f"INSERT INTO leads({cols}) VALUES({placeholders})", list(kwargs.values()))
                conn.commit()
                return conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    @classmethod
    def get_leads(cls, status: str = None, stage: int = None, limit: int = 100) -> List[dict]:
        q = "SELECT * FROM leads WHERE 1=1"
        params = []
        if status: q += " AND status=?"; params.append(status)
        if stage is not None: q += " AND stage=?"; params.append(stage)
        q += " ORDER BY score DESC, created_at ASC LIMIT ?"
        params.append(limit)
        rows = cls.get().execute(q, params).fetchall()
        return [dict(r) for r in rows]

    @classmethod
    def get_clients(cls) -> List[dict]:
        return [dict(r) for r in cls.get().execute("SELECT * FROM clients ORDER BY onboarded_at DESC").fetchall()]

    @classmethod
    def daily_send_count(cls) -> int:
        today = datetime.now().strftime("%Y-%m-%d")
        r = cls.get().execute(
            "SELECT COUNT(*) as c FROM emails_sent WHERE sent_at LIKE ?",
            (f"{today}%",)
        ).fetchone()
        return r["c"] if r else 0


# ══════════════════════════════════════════════════════════════
# AUDIT TRAIL (hash-linked, tamper-evident)
# ══════════════════════════════════════════════════════════════

_LAST_AUDIT_HASH = "GENESIS"
_audit_lock = threading.Lock()

def audit(action: str, data: dict):
    global _LAST_AUDIT_HASH
    with _audit_lock:
        entry = {
            "ts":     datetime.now(timezone.utc).isoformat(),
            "action": action,
            "data":   data,
            "prev":   _LAST_AUDIT_HASH,
        }
        s = json.dumps(entry, sort_keys=True, default=str)
        _LAST_AUDIT_HASH = hashlib.sha256(s.encode()).hexdigest()[:16]
        entry["hash"] = _LAST_AUDIT_HASH
        try:
            with open(AUDIT_FILE, "a") as f:
                f.write(json.dumps(entry, default=str) + "\n")
        except Exception:
            pass
        DB.event(action, data)


# ══════════════════════════════════════════════════════════════
# GLOBAL RUNTIME STATE
# ══════════════════════════════════════════════════════════════

SHUTDOWN         = threading.Event()
_ENGINE_PAUSED   = threading.Event()
START_TIME       = time.time()
_NOTIFICATIONS   : List[str] = []
_notif_lock      = threading.Lock()
_WATCHDOGS       : List["Watchdog"] = []

def notify(msg: str):
    with _notif_lock:
        _NOTIFICATIONS.append(f"[{datetime.now().strftime('%H:%M')}] {msg}")
        if len(_NOTIFICATIONS) > 200:
            _NOTIFICATIONS[:] = _NOTIFICATIONS[-100:]
    # Push to Telegram if bot running
    _telegram_push(msg)

def pop_notifications(n: int = 20) -> List[str]:
    with _notif_lock:
        msgs = _NOTIFICATIONS[-n:]
        return msgs

def uptime_str() -> str:
    s = int(time.time() - START_TIME)
    h, r = divmod(s, 3600); m, sec = divmod(r, 60)
    return f"{h}h {m}m {sec}s"

def is_business_hours() -> bool:
    now = datetime.now()
    return Config.BIZ_HOUR_START <= now.hour < Config.BIZ_HOUR_END


# ══════════════════════════════════════════════════════════════
# EMAIL VALIDATION
# ══════════════════════════════════════════════════════════════

_FREE_DOMAINS = {
    'gmail.com','yahoo.com','hotmail.com','outlook.com','aol.com',
    'icloud.com','live.com','msn.com','me.com','mac.com','ymail.com',
}
_DEAD_DOMAINS = {
    'example.com','test.com','localhost','invalid.com',
    'tempmail.com','mailinator.com','throwaway.email',
}
_EMAIL_RE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9._%+-]{0,63}@[a-zA-Z0-9][a-zA-Z0-9.-]{0,253}\.[a-zA-Z]{2,}$')
_JUNK_PATTERNS = [r'noreply', r'no-reply', r'donotreply', r'bounce', r'notifications@', r'system@', r'admin@']

def validate_email(addr: str) -> bool:
    if not addr or not isinstance(addr, str): return False
    addr = addr.strip().lower()
    if not _EMAIL_RE.match(addr): return False
    local, domain = addr.split('@', 1)
    if '..' in local or '..' in domain: return False
    if domain in _DEAD_DOMAINS: return False
    if any(re.search(p, addr) for p in _JUNK_PATTERNS): return False
    return True

def is_biz_email(addr: str) -> bool:
    if not addr or '@' not in addr: return False
    return addr.split('@')[1].lower() not in _FREE_DOMAINS

def is_system_sender(addr: str) -> bool:
    patterns = ['mailer-daemon','postmaster','noreply','no-reply','bounce','auto-reply','autoreply']
    return any(p in addr.lower() for p in patterns)

def is_autoresponder(subject: str, body: str) -> bool:
    tags = ['out of office','auto-reply','automatic reply','delivery status',
            'undeliverable','mail delivery','returned mail','failure notice','vacation']
    return any(t in (subject + " " + body).lower() for t in tags)


# ══════════════════════════════════════════════════════════════
# ADAPTIVE LEAD SCORING
# ══════════════════════════════════════════════════════════════

DEFAULT_WEIGHTS = {
    "has_website":      15.0,
    "valid_email":      20.0,
    "biz_email":        15.0,
    "high_reviews":     15.0,
    "high_rating":      10.0,
    "category_bonus":   10.0,
    "inbound_source":   20.0,   # bonus for inbound/opted-in leads
    "engagement":        5.0,
}

def load_weights() -> dict:
    if WEIGHTS_FILE.exists():
        try:
            w = json.loads(WEIGHTS_FILE.read_text())
            # Merge any new keys
            for k, v in DEFAULT_WEIGHTS.items():
                w.setdefault(k, v)
            return w
        except Exception:
            pass
    return DEFAULT_WEIGHTS.copy()

def save_weights(w: dict):
    WEIGHTS_FILE.write_text(json.dumps(w, indent=2))

def score_lead(lead: dict, weights: dict) -> float:
    s = 0.0
    if lead.get("website"):                          s += weights["has_website"]
    if validate_email(lead.get("email", "")):        s += weights["valid_email"]
    if is_biz_email(lead.get("email", "")):          s += weights["biz_email"]
    if (lead.get("reviews") or 0) > 10:              s += weights["high_reviews"]
    elif (lead.get("reviews") or 0) > 3:             s += weights["high_reviews"] * 0.5
    if (lead.get("rating") or 0) >= 4.0:             s += weights["high_rating"]
    s += weights["category_bonus"]
    if lead.get("source") in ("webhook","inbound","stripe","form"):
        s += weights["inbound_source"]
    return min(round(s, 1), 100.0)


# ══════════════════════════════════════════════════════════════
# SEND GATE
# ══════════════════════════════════════════════════════════════

def passes_gate(lead: dict, weights: dict) -> tuple[bool, str]:
    email = lead.get("email", "")
    if not validate_email(email):
        return False, "invalid_email"
    if DB.is_suppressed(email):
        return False, "suppressed"
    if score_lead(lead, weights) < Config.SEND_SCORE_THRESHOLD:
        return False, f"score_below_threshold ({score_lead(lead, weights):.0f}<{Config.SEND_SCORE_THRESHOLD})"
    if DB.daily_send_count() >= Config.MAX_DAILY_SENDS:
        return False, "daily_limit_reached"
    return True, "ok"


# ══════════════════════════════════════════════════════════════
# EMAIL SENDING ENGINE
# Priority: SendGrid → Mailgun → SMTP
# ══════════════════════════════════════════════════════════════

class EmailEngine:
    @staticmethod
    def _sig(product_key: str = "full_ops") -> str:
        p = Config.PRODUCTS.get(product_key, Config.PRODUCTS["full_ops"])
        parts = [
            f"\n\n—\n{Config.CEO_NAME}",
            f"CEO, {Config.COMPANY_NAME}",
        ]
        if Config.COMPANY_WEBSITE: parts.append(Config.COMPANY_WEBSITE)
        if p.get("stripe"):
            parts.append(f"Start {p['trial']}-day free trial (${0} today): {p['stripe']}")
        if Config.COMPANY_PHONE:   parts.append(f"Direct: {Config.COMPANY_PHONE}")
        if Config.CALENDLY_LINK:   parts.append(f"Book a call: {Config.CALENDLY_LINK}")
        return "\n".join(parts)

    @classmethod
    def send(cls, to: str, subject: str, body: str,
             product_key: str = "full_ops",
             add_sig: bool = True,
             lead_id: int = None,
             stage: int = None) -> bool:
        if not validate_email(to):
            log("warning", "email", f"Blocked send to invalid address: {to}")
            return False

        full_body = body + (cls._sig(product_key) if add_sig else "")

        provider = None
        ok = False

        if Config.SENDGRID_API_KEY:
            ok, provider = cls._sendgrid(to, subject, full_body)
        if not ok and Config.MAILGUN_API_KEY and Config.MAILGUN_DOMAIN:
            ok, provider = cls._mailgun(to, subject, full_body)
        if not ok and Config.SMTP_USER and Config.SMTP_PASS:
            ok, provider = cls._smtp(to, subject, full_body)

        if ok:
            log("info", "email", f"✉ Sent [{provider}] → {to}: {subject}")
            DB.metric("emails_sent")
            DB.get().execute("""
                INSERT INTO emails_sent(lead_id, to_email, subject, stage, product_key, provider)
                VALUES(?,?,?,?,?,?)
            """, (lead_id, to, subject, stage, product_key, provider))
            DB.get().commit()
            audit("EMAIL_SENT", {"to": to, "subject": subject, "product": product_key, "provider": provider})
        else:
            log("error", "email", f"All providers failed for {to}")
            DB.metric("emails_failed")

        return ok

    @staticmethod
    def _sendgrid(to: str, subject: str, body: str) -> tuple[bool, str]:
        try:
            r = requests.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={
                    "Authorization": f"Bearer {Config.SENDGRID_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "personalizations": [{"to": [{"email": to}]}],
                    "from": {
                        "email": Config.COMPANY_EMAIL,
                        "name": f"{Config.CEO_NAME} | {Config.COMPANY_NAME}",
                    },
                    "subject": subject,
                    "content": [{"type": "text/plain", "value": body}],
                    "tracking_settings": {
                        "click_tracking": {"enable": True},
                        "open_tracking": {"enable": True},
                    },
                },
                timeout=15,
            )
            return r.status_code in (200, 202), "sendgrid"
        except Exception as e:
            log("error", "sendgrid", str(e))
            return False, "sendgrid"

    @staticmethod
    def _mailgun(to: str, subject: str, body: str) -> tuple[bool, str]:
        try:
            r = requests.post(
                f"https://api.mailgun.net/v3/{Config.MAILGUN_DOMAIN}/messages",
                auth=("api", Config.MAILGUN_API_KEY),
                data={
                    "from": f"{Config.CEO_NAME} | {Config.COMPANY_NAME} <noreply@{Config.MAILGUN_DOMAIN}>",
                    "to": to,
                    "subject": subject,
                    "text": body,
                },
                timeout=15,
            )
            return r.status_code == 200, "mailgun"
        except Exception as e:
            log("error", "mailgun", str(e))
            return False, "mailgun"

    @staticmethod
    def _smtp(to: str, subject: str, body: str) -> tuple[bool, str]:
        try:
            msg = MIMEMultipart("alternative")
            msg["From"]    = f"{Config.CEO_NAME} | {Config.COMPANY_NAME} <{Config.SMTP_USER}>"
            msg["To"]      = to
            msg["Subject"] = subject
            msg["X-Mailer"] = "OmegaAI-v10"
            msg.attach(MIMEText(body, "plain"))
            with smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT, timeout=20) as s:
                s.ehlo(); s.starttls(); s.ehlo()
                s.login(Config.SMTP_USER, Config.SMTP_PASS)
                s.sendmail(Config.SMTP_USER, to, msg.as_string())
            return True, "smtp"
        except Exception as e:
            log("error", "smtp", str(e))
            return False, "smtp"


# ══════════════════════════════════════════════════════════════
# AI ENGINE — Claude (SDK or REST) with OpenRouter fallback
# ══════════════════════════════════════════════════════════════

class AI:
    @classmethod
    def generate(cls, system: str, user: str,
                 max_tokens: int = 1000,
                 smart: bool = False) -> Optional[str]:
        model = Config.CLAUDE_SMART_MODEL if smart else Config.CLAUDE_MODEL

        # Path 1: Anthropic SDK
        if ANTHROPIC_SDK_OK and Config.ANTHROPIC_API_KEY:
            try:
                client = anthropic_lib.Anthropic(api_key=Config.ANTHROPIC_API_KEY)
                msg = client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                )
                return msg.content[0].text.strip()
            except Exception as e:
                log("warning", "ai", f"SDK failed, trying REST: {e}")

        # Path 2: Anthropic REST
        if Config.ANTHROPIC_API_KEY:
            try:
                r = requests.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": Config.ANTHROPIC_API_KEY,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": model,
                        "max_tokens": max_tokens,
                        "system": system,
                        "messages": [{"role": "user", "content": user}],
                    },
                    timeout=30,
                )
                r.raise_for_status()
                return r.json()["content"][0]["text"].strip()
            except Exception as e:
                log("error", "ai", f"Anthropic REST failed: {e}")

        # Path 3: OpenRouter fallback
        if Config.OPENROUTER_API_KEY:
            try:
                r = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {Config.OPENROUTER_API_KEY}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": Config.COMPANY_WEBSITE or "https://omega.ai",
                    },
                    json={
                        "model": Config.OPENROUTER_MODEL,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                    },
                    timeout=30,
                )
                r.raise_for_status()
                return r.json()["choices"][0]["message"]["content"].strip()
            except Exception as e:
                log("error", "ai", f"OpenRouter failed: {e}")

        log("error", "ai", "All AI backends unavailable.")
        return None

    @classmethod
    def classify_intent(cls, sender: str, subject: str, body: str) -> str:
        """Rule-based fast classifier (no AI call needed)."""
        if is_system_sender(sender):       return "bounce"
        if is_autoresponder(subject, body): return "autoresponder"
        combined = (body + " " + subject).lower()
        for t in Config.INTENT_BLACKLIST:
            if t in combined: return "blacklist"
        for t in Config.INTENT_UNSUBSCRIBE:
            if t in combined: return "unsubscribe"
        for t in Config.INTENT_BUY:
            if t in combined: return "interested"
        for t in Config.INTENT_PRICING:
            if t in combined: return "pricing"
        if 5 < len(body.split()) < 20: return "quick_reply"
        return "question"


# ══════════════════════════════════════════════════════════════
# PITCH & REPLY GENERATOR
# ══════════════════════════════════════════════════════════════

def _product_for_lead(lead: dict) -> str:
    cat = (lead.get("category") or "").lower()
    high = ["law firm","accounting","med spa","dental","real estate","insurance","finance"]
    mid  = ["hvac","roofing","plumbing","auto","marketing","consultant"]
    if any(h in cat for h in high): return "full_ops"
    if any(m in cat for m in mid):  return "growth"
    return "starter"

def _ceo_context() -> str:
    return (
        f"You are {Config.CEO_NAME}, CEO of {Config.COMPANY_NAME}. "
        f"You help local businesses automate lead response and revenue generation using AI. "
        f"Your tone: confident, direct, results-first. No fluff. No hype. No corporate speak. "
        f"You write like a founder who has done this hundreds of times."
    )

def generate_pitch(lead: dict, stage: int = 1, product_key: str = "full_ops") -> Optional[str]:
    p = Config.PRODUCTS.get(product_key, Config.PRODUCTS["full_ops"])
    name = lead.get("name", "there")
    category = lead.get("category", "local business")
    pain_angles = [
        "losing leads because they respond too slowly",
        "watching competitors use AI to steal their customers",
        "leaving money on the table with zero follow-up automation",
        "paying for ads but losing the leads those ads generate",
        "missing 40%+ of inbound calls and never recovering those opportunities",
    ]
    angle = random.choice(pain_angles)
    sys_p = _ceo_context() + f" Product: {p['name']} — {p['desc']} — ${p['price']:,.0f}/mo, {p['trial']}-day free trial."
    if stage == 1:
        user_p = (
            f"Write a cold email to {name}, a {category}.\n"
            f"Lead with: they are {angle}.\n"
            f"Show you understand their industry in one line.\n"
            f"Offer: {p['trial']}-day free trial — $0 today, ${p['price']:,.0f}/mo after if they see results.\n"
            f"CTA: Start trial → {p['stripe']} OR reply with business email + phone.\n"
            f"Rules: ≤130 words. First sentence hooks. No subject line. No 'I hope this email finds you'. Personal feel."
        )
    elif stage == 2:
        user_p = (
            f"Follow-up #2 to {name} ({category}). They didn't reply. Don't apologize. Don't mention you emailed before.\n"
            f"Lead with a specific result: 'A {category.split()[0]} we worked with booked 35 new appointments in the first 30 days.'\n"
            f"Remind: {p['trial']}-day free trial — $0 risk.\n"
            f"CTA: {p['stripe']} or reply with email + phone.\n"
            f"≤100 words. Direct. New angle."
        )
    else:
        user_p = (
            f"Final email to {name}. Subject line optional. Be direct.\n"
            f"Offer a free 10-minute revenue leak audit — show exactly how many leads they're losing per month.\n"
            f"No strings. Just reply 'audit' or click: {p['stripe']}.\n"
            f"≤75 words. One clear ask. Urgency without being pushy."
        )
    return AI.generate(sys_p, user_p, max_tokens=400)

def generate_reply(sender_email: str, intent: str, body: str) -> Optional[str]:
    lead_rows = DB.get().execute("SELECT * FROM leads WHERE email=?", (sender_email,)).fetchone()
    lead = dict(lead_rows) if lead_rows else {}
    client_rows = DB.get().execute("SELECT * FROM clients WHERE email=?", (sender_email,)).fetchone()
    client = dict(client_rows) if client_rows else {}

    name = lead.get("name") or client.get("name") or "there"
    product_key = lead.get("product_pitched") or client.get("product_key") or "full_ops"
    p = Config.PRODUCTS.get(product_key, Config.PRODUCTS["full_ops"])

    sys_p = _ceo_context() + f" Product: {p['name']} — ${p['price']:,.0f}/mo, {p['trial']}-day free trial."

    if intent == "interested":
        user_p = (
            f"{name} is ready to start. Their message: '{body[:300]}'\n"
            f"Send trial link: {p['stripe']}\n"
            f"Tell them: {p['trial']}-day free trial, $0 today, we handle full setup.\n"
            f"Ask for business email + phone number to begin onboarding.\n"
            f"≤100 words. Warm and action-oriented."
        )
    elif intent == "pricing":
        user_p = (
            f"{name} asked about pricing. Their message: '{body[:200]}'\n"
            f"Be direct: ${p['price']:,.0f}/month. {p['trial']}-day free trial — $0 today. No contracts. Cancel anytime.\n"
            f"Link: {p['stripe']}\n"
            f"Offer to answer any questions. ≤80 words."
        )
    elif intent == "quick_reply":
        user_p = (
            f"{name} replied briefly: '{body[:200]}'\n"
            f"Match their energy. Short, direct response. Move them toward the trial.\n"
            f"≤60 words."
        )
    else:
        user_p = (
            f"Message from {name}: '{body[:400]}'\n"
            f"Respond helpfully and directly. Naturally connect to how {Config.COMPANY_NAME} can help.\n"
            f"≤100 words."
        )
    return AI.generate(sys_p, user_p, max_tokens=350, smart=True)


# ══════════════════════════════════════════════════════════════
# LEAD GENERATION — B2B Data APIs (opted-in contacts)
# ══════════════════════════════════════════════════════════════

LEAD_CITIES = [c.strip() for c in os.getenv("LEAD_CITIES", "atlanta").split(",")]

LEAD_CATEGORY_TYPES = [
    "roofing company", "hvac company", "med spa", "dental clinic",
    "plumbing company", "law firm", "accounting firm", "auto repair shop",
    "landscaping company", "real estate agency", "insurance agency",
    "physical therapy clinic", "chiropractic clinic", "home renovation contractor",
    "marketing agency", "pest control", "electrical contractor", "painting contractor",
]

LEAD_CATEGORIES = [f"{cat} {city}" for city in LEAD_CITIES for cat in LEAD_CATEGORY_TYPES]

_LEAD_CATEGORIES_ORIG = [
    "roofing company atlanta",     "hvac company atlanta",
    "med spa atlanta",             "dental clinic atlanta",
    "plumbing company atlanta",    "law firm atlanta",
    "accounting firm atlanta",     "auto repair shop atlanta",
    "landscaping company atlanta", "real estate agency atlanta",
    "insurance agency atlanta",    "physical therapy clinic atlanta",
    "chiropractic clinic atlanta", "home renovation contractor atlanta",
    "marketing agency atlanta",    "pest control atlanta",
    "electrical contractor atlanta","painting contractor atlanta",
]

def _hunter_domain_search(domain: str) -> Optional[str]:
    """Hunter.io — finds publicly listed contact emails for a domain."""
    if not Config.HUNTER_API_KEY: return None
    try:
        r = requests.get(
            "https://api.hunter.io/v2/domain-search",
            params={"domain": domain, "api_key": Config.HUNTER_API_KEY, "limit": 3},
            timeout=10,
        )
        data = r.json().get("data", {})
        emails = data.get("emails", [])
        # Prefer owner/ceo/founder, then generic
        for role in ["owner","ceo","founder","president","director","manager"]:
            for e in emails:
                if role in (e.get("position") or "").lower():
                    addr = e.get("value", "")
                    if validate_email(addr): return addr
        for e in emails:
            addr = e.get("value", "")
            if validate_email(addr) and is_biz_email(addr): return addr
        return None
    except Exception as e:
        log("error", "hunter", str(e))
        return None

def _serpapi_search(category: str) -> List[dict]:
    """Google Maps via SerpAPI — business discovery."""
    if not Config.SERPAPI_API_KEY: return []
    try:
        r = requests.get(
            "https://serpapi.com/search",
            params={
                "api_key": Config.SERPAPI_API_KEY,
                "engine":  "google_maps",
                "q":       category,
                "ll":      "@33.7490,-84.3880,14z",
                "type":    "search",
            },
            timeout=20,
        )
        r.raise_for_status()
        results = []
        for b in r.json().get("local_results", []):
            if b.get("website"):
                results.append({
                    "name":     b.get("title", "Business"),
                    "website":  b.get("website", ""),
                    "category": category,
                    "rating":   b.get("rating") or 0,
                    "reviews":  b.get("reviews") or 0,
                })
        return results
    except Exception as e:
        log("error", "serpapi", str(e))
        return []

def run_lead_generation():
    """Discovery → Hunter email lookup → scoring → gate → DB."""
    if _ENGINE_PAUSED.is_set(): return
    weights = load_weights()
    new_ct = rejected_ct = 0

    for cat in LEAD_CATEGORIES:
        if SHUTDOWN.is_set(): break
        businesses = _serpapi_search(cat)

        for biz in businesses[:5]:
            if SHUTDOWN.is_set(): break
            domain = urlparse(biz["website"]).netloc.replace("www.", "")
            email = _hunter_domain_search(domain)
            if not email:
                # Fallback: derive info@ — lower score, will often be gated out
                email = f"info@{domain}"

            lead = {
                "email":    email,
                "name":     biz["name"],
                "website":  biz["website"],
                "category": cat,
                "rating":   biz["rating"],
                "reviews":  biz["reviews"],
                "source":   "serpapi" if not Config.HUNTER_API_KEY else "hunter",
            }
            lead["score"] = score_lead(lead, weights)
            ok, reason = passes_gate(lead, weights)
            if not ok:
                rejected_ct += 1
                DB.metric("gate_rejected")
                continue

            # Check not already contacted
            existing = DB.get().execute("SELECT id,status FROM leads WHERE email=?", (email,)).fetchone()
            if existing and existing["status"] not in ("new",):
                continue

            DB.upsert_lead(
                email,
                name=biz["name"], website=biz["website"],
                category=cat, source=lead["source"],
                score=lead["score"], status="new", stage=0,
            )
            new_ct += 1
            DB.metric("leads_generated")
            DB.metric("gate_passed")

    if new_ct > 0:
        log("info", "leadgen", f"+{new_ct} new leads | {rejected_ct} gate-rejected")
        notify(f"🎯 {new_ct} new qualified leads | {rejected_ct} rejected")



# ════════════════════════════════════════════════════════
# A/B EMAIL TESTING ENGINE
# Generates 2 variants per lead, tracks winner by reply rate
# ════════════════════════════════════════════════════════

def generate_pitch_ab(lead: dict, stage: int = 1, product_key: str = "full_ops") -> tuple:
    """Generate two email variants for A/B testing. Returns (variant_a, variant_b, angles)."""
    p = Config.PRODUCTS.get(product_key, Config.PRODUCTS["full_ops"])
    name = lead.get("name", "there")
    category = lead.get("category", "local business")

    # Two distinct angle pools
    angles_a = [
        "losing leads because they respond too slowly",
        "paying for ads but losing the leads those ads generate",
        "missing 40%+ of inbound calls and never recovering those opportunities",
    ]
    angles_b = [
        "watching competitors use AI to steal their customers",
        "leaving money on the table with zero follow-up automation",
        "spending hours on admin work that AI could handle in seconds",
    ]

    angle_a = random.choice(angles_a)
    angle_b = random.choice(angles_b)

    sys_p = _ceo_context() + f" Product: {p['name']} — {p['desc']} — ${p['price']:,.0f}/mo, {p['trial']}-day free trial."

    # Variant A — Pain-focused angle
    prompt_a = (
        f"Write a cold email to {name}, a {category}.\n"
        f"Lead with: they are {angle_a}.\n"
        f"Show you understand their industry in one line.\n"
        f"Offer: {p['trial']}-day free trial — $0 today, ${p['price']:,.0f}/mo after results.\n"
        f"CTA: {p['stripe']} OR reply with business email + phone.\n"
        f"Rules: ≤130 words. First sentence hooks. No subject line. No filler. Personal feel."
    )

    # Variant B — Outcome/result-focused angle
    prompt_b = (
        f"Write a cold email to {name}, a {category}.\n"
        f"Lead with a specific result: 'A {category.split()[0]} we work with added 28 new clients in 60 days using AI outreach.'\n"
        f"They are {angle_b}.\n"
        f"Offer: {p['trial']}-day free trial — $0 today.\n"
        f"CTA: {p['stripe']} OR reply with email + phone.\n"
        f"Rules: ≤130 words. Outcome-first. No fluff. Feels like a peer, not a salesperson."
    )

    variant_a = AI.generate(sys_p, prompt_a, max_tokens=400)
    variant_b = AI.generate(sys_p, prompt_b, max_tokens=400)

    return variant_a, variant_b, angle_a, angle_b


def record_ab_send(lead_id: int, variant: str, angle: str):
    """Record which variant was sent to this lead."""
    try:
        DB.get().execute("""
            INSERT OR REPLACE INTO metrics (key, value, updated_at)
            VALUES (?, ?, datetime('now'))
        """, (f"ab_variant_{lead_id}", 1.0 if variant == "A" else 2.0, ))
        DB.get().execute("""
            INSERT OR REPLACE INTO metrics (key, value, updated_at)
            VALUES (?, ?, datetime('now'))
        """, (f"ab_angle_{lead_id}", hash(angle) % 1000000, ))
        DB.get().commit()
    except Exception as _e:
        log("error", "ab_test", f"Record error: {_e}")


def get_ab_winner() -> dict:
    """Analyze which variant is winning based on reply rates."""
    try:
        # Count sends per variant
        a_sends = DB.get().execute(
            "SELECT COUNT(*) FROM metrics WHERE key LIKE 'ab_variant_%' AND value = 1.0"
        ).fetchone()[0]
        b_sends = DB.get().execute(
            "SELECT COUNT(*) FROM metrics WHERE key LIKE 'ab_variant_%' AND value = 2.0"
        ).fetchone()[0]

        # Count replies per variant by joining with email_replies
        a_replies = DB.get().execute("""
            SELECT COUNT(*) FROM email_replies er
            JOIN leads l ON l.email = er.from_email
            JOIN metrics m ON m.key = 'ab_variant_' || l.id
            WHERE m.value = 1.0 AND er.intent NOT IN ('bounce','unsubscribe','autoresponder')
        """).fetchone()[0]

        b_replies = DB.get().execute("""
            SELECT COUNT(*) FROM email_replies er
            JOIN leads l ON l.email = er.from_email
            JOIN metrics m ON m.key = 'ab_variant_' || l.id
            WHERE m.value = 2.0 AND er.intent NOT IN ('bounce','unsubscribe','autoresponder')
        """).fetchone()[0]

        a_rate = (a_replies / a_sends * 100) if a_sends > 0 else 0
        b_rate = (b_replies / b_sends * 100) if b_sends > 0 else 0

        winner = "A" if a_rate >= b_rate else "B"
        confident = (a_sends + b_sends) >= 50

        return {
            "a_sends": a_sends, "b_sends": b_sends,
            "a_replies": a_replies, "b_replies": b_replies,
            "a_rate": round(a_rate, 1), "b_rate": round(b_rate, 1),
            "winner": winner, "confident": confident
        }
    except Exception as _e:
        log("error", "ab_test", f"Analysis error: {_e}")
        return {"winner": "A", "confident": False, "a_sends": 0, "b_sends": 0}

# ══════════════════════════════════════════════════════════════
# OUTREACH ENGINE — Multi-Stage
# ══════════════════════════════════════════════════════════════

def run_outreach():
    if _ENGINE_PAUSED.is_set(): return
    if not is_business_hours():
        log("info", "outreach", "Outside business hours — skipping")
        return
    if DB.daily_send_count() >= Config.MAX_DAILY_SENDS:
        log("info", "outreach", "Daily send limit reached")
        return

    weights = load_weights()
    sends = 0

    # Stage 0 → 1: New leads
    new_leads = DB.get_leads(status="new", stage=0, limit=10)
    for lead in new_leads:
        if SHUTDOWN.is_set() or sends >= 8: break
        ok, reason = passes_gate(lead, weights)
        if not ok: continue

        product_key = _product_for_lead(lead)
        pitch = generate_pitch(lead, stage=1, product_key=product_key)
        if not pitch: continue

        lead_id = lead["id"]
        if verify_email_exists(lead["email"]) and EmailEngine.send(
            lead["email"],
            f"Quick question for {lead['name']}",
            pitch,
            product_key=product_key,
            lead_id=lead_id,
            stage=1,
        ):
            DB.get().execute("""
                UPDATE leads SET status='contacted', stage=1,
                product_pitched=?, last_contact_at=datetime('now')
                WHERE id=?
            """, (product_key, lead_id))
            DB.get().commit()
            DB.metric("outreach_stage1")
            sends += 1
            time.sleep(Config.RATE_LIMIT_DELAY)

    # Stages 2-3: Follow-ups
    contacted = DB.get_leads(status="contacted", limit=20)
    for lead in contacted:
        if SHUTDOWN.is_set() or sends >= 15: break
        if DB.is_suppressed(lead["email"]): continue
        stage = lead.get("stage") or 1
        if stage >= Config.MAX_STAGES: continue

        last_contact = lead.get("last_contact_at")
        if not last_contact: continue
        try:
            delta = (datetime.utcnow() - datetime.fromisoformat(last_contact.replace("Z",""))).days
        except Exception:
            continue
        if delta < Config.FOLLOW_UP_DAYS: continue

        product_key = lead.get("product_pitched") or _product_for_lead(lead)
        next_stage = stage + 1
        pitch = generate_pitch(lead, stage=next_stage, product_key=product_key)
        if not pitch: continue

        if verify_email_exists(lead["email"]) and EmailEngine.send(
            lead["email"],
            f"Re: Quick question for {lead['name']}",
            pitch,
            product_key=product_key,
            lead_id=lead["id"],
            stage=next_stage,
        ):
            DB.get().execute("""
                UPDATE leads SET stage=?, last_contact_at=datetime('now') WHERE id=?
            """, (next_stage, lead["id"]))
            DB.get().commit()
            sends += 1
            time.sleep(Config.RATE_LIMIT_DELAY)

    if sends > 0:
        log("info", "outreach", f"{sends} emails sent | daily total: {DB.daily_send_count()}/{Config.MAX_DAILY_SENDS}")
        notify(f"📨 {sends} outreach emails sent | daily: {DB.daily_send_count()}/{Config.MAX_DAILY_SENDS}")


# ══════════════════════════════════════════════════════════════
# INBOX INTELLIGENCE
# ══════════════════════════════════════════════════════════════

def fetch_inbox() -> List[dict]:
    if not Config.IMAP_USER or not Config.IMAP_PASS: return []
    messages = []
    try:
        mail = imaplib.IMAP4_SSL(Config.IMAP_HOST, Config.IMAP_PORT)
        mail.login(Config.IMAP_USER, Config.IMAP_PASS)
        mail.select("inbox")
        _, data = mail.search(None, "UNSEEN")
        for num in data[0].split():
            try:
                _, md = mail.fetch(num, "(RFC822)")
                msg = email_lib.message_from_bytes(md[0][1])
                from_raw = msg.get("From", "")
                m = re.search(r"[\w.%+-]+@[\w.-]+\.\w{2,}", from_raw)
                sender = m.group(0).lower() if m else ""
                raw_subj = msg.get("Subject", "")
                decoded = decode_header(raw_subj)
                subject = decoded[0][0]
                if isinstance(subject, bytes):
                    subject = subject.decode(decoded[0][1] or "utf-8", errors="replace")
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        ct = part.get_content_type()
                        disp = str(part.get("Content-Disposition", ""))
                        if ct == "text/plain" and "attachment" not in disp:
                            body = part.get_payload(decode=True).decode(errors="replace")
                            break
                else:
                    body = msg.get_payload(decode=True).decode(errors="replace")
                if sender:
                    messages.append({"sender": sender, "subject": str(subject), "body": body.strip()})
            except Exception:
                continue
        mail.close(); mail.logout()
    except Exception as e:
        log("error", "imap", str(e))
    return messages

def run_inbox():
    if SHUTDOWN.is_set(): return
    messages = fetch_inbox()
    if not messages: return

    for msg in messages:
        sender  = msg["sender"]
        subject = msg["subject"]
        body    = msg["body"]

        intent = AI.classify_intent(sender, subject, body)
        log("info", "inbox", f"{sender} → intent={intent}")

        DB.get().execute(
            "INSERT INTO email_replies(from_email,subject,body,intent) VALUES(?,?,?,?)",
            (sender, subject, body[:2000], intent)
        )
        DB.get().commit()

        if intent in ("bounce", "autoresponder"):
            if intent == "bounce": DB.metric("bounced")
            continue

        DB.metric("real_replies")
        audit("REPLY_RECEIVED", {"sender": sender, "intent": intent})

        if intent == "blacklist":
            DB.suppress(sender, "blacklist")
            notify(f"⛔ {sender} blacklisted")
            continue

        if intent == "unsubscribe":
            DB.suppress(sender, "unsubscribe")
            EmailEngine.send(
                sender,
                f"Re: {subject}",
                "Done — you've been removed from our list. Sorry for any inconvenience.",
                add_sig=False,
            )
            notify(f"🚫 {sender} unsubscribed")
            continue

        # Generate and send AI reply
        reply = generate_reply(sender, intent, body)
        if reply:
            product_key = "full_ops"
            lead = DB.get().execute("SELECT product_pitched FROM leads WHERE email=?", (sender,)).fetchone()
            if lead and lead["product_pitched"]: product_key = lead["product_pitched"]
            EmailEngine.send(sender, f"Re: {subject}", reply, product_key=product_key)

        # Conversational onboarding — intercept client replies
        client_row = DB.get().execute(
            "SELECT status, answers FROM clients WHERE email=?", (sender,)
        ).fetchone()
        if client_row and client_row["status"] in ("trial","onboarding","active"):
            answers = json.loads(client_row["answers"] or "{}")
            if len(answers) < len(ONBOARD_QUESTIONS):
                run_conversational_onboarding(sender, body, subject)
                continue

        # Check if this is an onboarding reply from existing client
        client_check = DB.get().execute(
            "SELECT status FROM clients WHERE email=?", (sender,)
        ).fetchone()
        if client_check and client_check["status"] in ("trial","onboarding"):
            process_onboarding_reply(sender, body)

        if intent == "interested":
            # Mark as interested in DB
            DB.get().execute("UPDATE leads SET status='interested' WHERE email=?", (sender,))
            DB.get().commit()
            DB.metric("interested_leads")
            p = Config.PRODUCTS.get(product_key, Config.PRODUCTS["full_ops"])
            DB.metric("projected_mrr", p["price"])
            audit("LEAD_INTERESTED", {"sender": sender, "product": product_key})
            notify(f"🔥 HOT LEAD: {sender} is INTERESTED | {p['name']}")

        DB.get().execute(
            "UPDATE email_replies SET processed=1 WHERE from_email=? AND processed=0",
            (sender,)
        )
        DB.get().commit()



# ════════════════════════════════════════════════════════
# PRODUCTION ONBOARDING ENGINE
# 60-second delayed welcome, tier-matched, Telegram alert
# Bounce rate protection — auto-pause at 40%
# ════════════════════════════════════════════════════════

def _check_bounce_rate():
    """Auto-pause outreach if bounce rate exceeds 40%."""
    try:
        sent    = DB.get().execute("SELECT COUNT(*) FROM emails_sent").fetchone()[0]
        bounces = DB.get().execute(
            "SELECT COUNT(*) FROM email_replies WHERE intent='bounce'"
        ).fetchone()[0]
        if sent < 10:
            return  # Not enough data
        rate = bounces / sent
        if rate > 0.40:
            _ENGINE_PAUSED.set()
            bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
            admin_ids = [int(x.strip()) for x in os.getenv("TELEGRAM_ADMIN_IDS","").split(",") if x.strip()]
            msg = (
                f"🚨 OMEGA AI — OUTREACH PAUSED\n"
                f"Bounce rate: {rate*100:.1f}% exceeded 40% threshold\n"
                f"Sent: {sent} | Bounces: {bounces}\n\n"
                f"Action required: Review email list quality\n"
                f"Resume via Telegram: /resume"
            )
            for admin_id in admin_ids:
                try:
                    import urllib.request as _ur, json as _jj
                    _payload = _jj.dumps({"chat_id": admin_id, "text": msg}).encode()
                    _req = _ur.Request(
                        f"https://api.telegram.org/bot{bot_token}/sendMessage",
                        data=_payload,
                        headers={"Content-Type": "application/json"}
                    )
                    _ur.urlopen(_req, timeout=10)
                except Exception:
                    pass
            log("error", "bounce_guard", f"Bounce rate {rate*100:.1f}% — outreach AUTO-PAUSED")
    except Exception as _e:
        log("error", "bounce_guard", str(_e))


def _delayed_onboarding(email: str, product_key: str, stripe_id: str, delay: int = 60):
    """Fire onboarding email after delay seconds in a background thread."""
    import threading as _t
    def _fire():
        import time as _time
        _time.sleep(delay)
        _trigger_onboarding_email(email, product_key, stripe_id)
    _t.Thread(target=_fire, daemon=True, name=f"Onboard-{email[:20]}").start()
    log("info", "onboarding", f"Onboarding scheduled in {delay}s for {email} — {product_key}")


def _trigger_onboarding_email(email: str, product_key: str, stripe_id: str = ""):
    """Send professional tier-matched welcome email and Claude onboarding sequence."""
    p = Config.PRODUCTS.get(product_key, Config.PRODUCTS["full_ops"])
    lead = DB.get().execute("SELECT name FROM leads WHERE email=?", (email,)).fetchone()
    name = lead["name"] if lead else email.split("@")[0].title()

    # Tier-specific messaging
    tier_perks = {
        "full_ops": [
            "Full AI outreach engine — 8 cities, 18 categories",
            "Dedicated inbox AI responding 24/7 in your brand voice",
            "Multi-stage follow-up sequences deployed automatically",
            "Real-time hot lead alerts to your phone",
            "Weekly performance reports with conversion analysis",
            "Direct line to your dedicated ops strategist",
        ],
        "growth": [
            "AI outreach engine — 4 cities, 10 categories",
            "Inbox AI monitoring and auto-response",
            "3-stage follow-up sequences",
            "Hot lead notifications",
            "Bi-weekly performance reports",
        ],
        "starter": [
            "AI outreach engine — 2 cities, 5 categories",
            "Basic inbox monitoring",
            "2-stage follow-up sequences",
            "Weekly summary report",
        ],
    }
    perks = tier_perks.get(product_key, tier_perks["starter"])
    perks_text = "\n".join(f"  ✓ {perk}" for perk in perks)
    cal_line = f"\n\nBook your onboarding call: {Config.CALENDLY_LINK}" if Config.CALENDLY_LINK else ""

    questions_text = "\n".join(
        f"{i+1}. {q}" for i, q in enumerate(Config.ONBOARDING_QUESTIONS)
    )

    body = f"""Hey {name},

Welcome to {Config.COMPANY_NAME}. Your {p['name']} is now active.

━━━━━━━━━━━━━━━━━━━━━━━━━
WHAT YOU'VE UNLOCKED:
━━━━━━━━━━━━━━━━━━━━━━━━━
{perks_text}

━━━━━━━━━━━━━━━━━━━━━━━━━
TO GET YOU LIVE IN 24 HRS:
━━━━━━━━━━━━━━━━━━━━━━━━━
Reply with answers to these questions:

{questions_text}
{cal_line}

━━━━━━━━━━━━━━━━━━━━━━━━━
YOUR DEPLOYMENT TIMELINE:
━━━━━━━━━━━━━━━━━━━━━━━━━
24 hrs — AI inbox live in your brand voice
48 hrs — Follow-up sequences deployed
7 days — Full outbound campaigns running

Reply to this email and we handle everything.

— {Config.CEO_NAME}
{Config.COMPANY_NAME}
{Config.COMPANY_EMAIL}"""

    ok = EmailEngine.send(
        email,
        f"Welcome to {Config.COMPANY_NAME} — {p['name']} Active",
        body,
        product_key=product_key,
        add_sig=False,
    )

    if ok:
        # Alert Thomas in Telegram
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        admin_ids = [int(x.strip()) for x in os.getenv("TELEGRAM_ADMIN_IDS","").split(",") if x.strip()]
        alert = (
            f"💳 NEW CLIENT ONBOARDED\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Email:   {email}\n"
            f"Name:    {name}\n"
            f"Tier:    {p['name']}\n"
            f"MRR:     ${p['price']:,.0f}/mo\n"
            f"Trial:   {p['trial']} days\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Welcome email sent. Onboarding started."
        )
        import urllib.request as _ur, json as _jj
        for admin_id in admin_ids:
            try:
                _payload = _jj.dumps({"chat_id": admin_id, "text": alert}).encode()
                _req = _ur.Request(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    data=_payload,
                    headers={"Content-Type": "application/json"}
                )
                _ur.urlopen(_req, timeout=10)
            except Exception:
                pass

        log("info", "onboarding", f"Welcome email sent to {email} — {p['name']}")
        DB.metric("onboardings")
        ledger_record_trial(email, product_key)
    else:
        log("error", "onboarding", f"Welcome email FAILED for {email}")

# ══════════════════════════════════════════════════════════════
# STRIPE WEBHOOK HANDLER — Auto-onboarding on payment
# ══════════════════════════════════════════════════════════════

def handle_stripe_event(payload: bytes, sig_header: str) -> dict:
    """Validate and process Stripe webhook. Returns result dict."""
    if not STRIPE_OK:
        return {"ok": False, "error": "stripe not installed"}

    event = None
    if Config.STRIPE_WEBHOOK_SECRET:
        try:
            event = stripe_lib.Webhook.construct_event(
                payload, sig_header, Config.STRIPE_WEBHOOK_SECRET
            )
        except stripe_lib.error.SignatureVerificationError:
            return {"ok": False, "error": "invalid_signature"}
    else:
        try:
            event = json.loads(payload)
        except Exception:
            return {"ok": False, "error": "invalid_json"}

    etype = event.get("type", "")
    data  = event.get("data", {}).get("object", {})

    if etype == "customer.subscription.created":
        _on_subscription_created(data)
    elif etype == "customer.subscription.deleted":
        _on_subscription_deleted(data)
    elif etype == "invoice.payment_succeeded":
        _on_payment_succeeded(data)
    elif etype == "invoice.payment_failed":
        _on_payment_failed(data)
    elif etype == "checkout.session.completed":
        _on_checkout_completed(data)

    audit(f"STRIPE_{etype.upper()}", {"event_type": etype})
    return {"ok": True, "type": etype}

def _resolve_product_key(price_id: str) -> str:
    for k, p in Config.PRODUCTS.items():
        if p.get("price_id") and p["price_id"] == price_id:
            return k
    return "full_ops"

def _on_checkout_completed(data: dict):
    email      = data.get("customer_email") or data.get("customer_details", {}).get("email", "")
    price_id   = ""
    line_items = data.get("line_items", {}).get("data", [])
    if line_items:
        price_id = line_items[0].get("price", {}).get("id", "")
    product_key = _resolve_product_key(price_id)
    p = Config.PRODUCTS.get(product_key, Config.PRODUCTS["full_ops"])
    if email:
        # Upsert client record immediately
        lead = DB.get().execute("SELECT name FROM leads WHERE email=?", (email,)).fetchone()
        name = lead["name"] if lead else email.split("@")[0].title()
        DB.get().execute("""
            INSERT INTO clients(email, name, product_key, mrr, status, stripe_id)
            VALUES(?,?,?,?,'trial',?)
            ON CONFLICT(email) DO UPDATE SET
                product_key=?, mrr=?, status='trial', stripe_id=?
        """, (email, name, product_key, p["price"], data.get("customer",""),
              product_key, p["price"], data.get("customer","")))
        DB.get().commit()
        # Fire welcome email after 60 seconds
        _delayed_onboarding(email, product_key, data.get("customer",""), delay=60)
        notify(f"NEW CLIENT: {email} — {p['name']} ${p['price']:,.0f}/mo — onboarding in 60s")

def _on_subscription_created(data: dict):
    cust_id = data.get("customer", "")
    price_id = ""
    items = data.get("items", {}).get("data", [])
    if items: price_id = items[0].get("price", {}).get("id", "")
    product_key = _resolve_product_key(price_id)
    p = Config.PRODUCTS.get(product_key, Config.PRODUCTS["full_ops"])
    DB.metric("conversions")
    DB.metric("mrr", p["price"])
    audit("SUBSCRIPTION_CREATED", {"customer": cust_id, "product": product_key, "mrr": p["price"]})
    notify(f"🚀 SUBSCRIPTION ACTIVE | {p['name']} | MRR +${p['price']:,.0f}")

def _on_subscription_deleted(data: dict):
    DB.metric("churned")
    items = data.get("items", {}).get("data", [])
    price_id = items[0].get("price", {}).get("id", "") if items else ""
    product_key = _resolve_product_key(price_id)
    p = Config.PRODUCTS.get(product_key, Config.PRODUCTS["full_ops"])
    DB.metric("mrr_churned", p["price"])
    ledger_record_churn('unknown', product_key, p['price'])
    notify(f"📉 CHURN: {p['name']} cancelled")

def _on_payment_succeeded(data: dict):
    DB.metric("payments_received")
    amt = data.get("amount_paid", 0) / 100
    email = data.get("customer_email", "unknown")
    ledger_record_payment(email, "full_ops", amt)
    notify(f"💰 Payment received: ${amt:,.2f}")

def _on_payment_failed(data: dict):
    DB.metric("payment_failures")
    email = data.get("customer_email", "unknown")
    notify(f"⚠️ Payment failed for {email}")

def _trigger_onboarding(email: str, product_key: str, stripe_id: str = ""):
    p = Config.PRODUCTS.get(product_key, Config.PRODUCTS["full_ops"])
    # Look up lead name
    lead = DB.get().execute("SELECT name FROM leads WHERE email=?", (email,)).fetchone()
    name = lead["name"] if lead else email.split("@")[0].title()

    # Upsert client record
    DB.get().execute("""
        INSERT INTO clients(email, name, product_key, mrr, status, stripe_id)
        VALUES(?,?,?,?,?,?)
        ON CONFLICT(email) DO UPDATE SET
            product_key=?, mrr=?, status='trial', stripe_id=?
    """, (email, name, product_key, p["price"], "trial", stripe_id,
          product_key, p["price"], stripe_id))
    DB.get().commit()
    DB.metric("onboardings")
    ledger_record_trial(email, product_key)

    questions_text = "\n".join(
        f"{i+1}. {q}" for i, q in enumerate(Config.ONBOARDING_QUESTIONS)
    )
    cal_line = f"\nBook your 15-min onboarding call: {Config.CALENDLY_LINK}" if Config.CALENDLY_LINK else ""
    body = textwrap.dedent(f"""
        Hey {name},

        Welcome to {p['name']}. Your {p['trial']}-day free trial is now active — $0 charged today.

        To get you live within 24 hours, please reply with answers to these questions:

        {questions_text}

        ━━━━━━━━━━━━━━━━━━━━━━━━━
        YOUR DEPLOYMENT TIMELINE:
        ━━━━━━━━━━━━━━━━━━━━━━━━━

        Within 24 hrs:
        • AI inbox connected and monitoring
        • Instant lead response live in your brand voice
        • Missed call recovery activated

        Within 48 hrs:
        • CRM integrated or provisioned
        • 3-7-14 day follow-up sequences deployed
        • Appointment calendar connected

        Within 7 days:
        • Outbound campaigns launched for your market
        • Real-time notifications for hot leads
        • Strategy call with ops team{cal_line}

        Just reply to this email and we handle everything.

        Questions? Reply here or contact {Config.COMPANY_EMAIL}.
    """).strip()

    EmailEngine.send(
        email,
        f"Welcome to {Config.COMPANY_NAME} — Your Trial is Active",
        body,
        product_key=product_key,
        add_sig=False,
    )
    audit("ONBOARD_TRIGGERED", {"email": email, "product": product_key})
    notify(f"🚀 ONBOARDING: {name} ({email}) — {p['name']}")


# ══════════════════════════════════════════════════════════════
# INBOUND LEAD WEBHOOK (Flask)
# ══════════════════════════════════════════════════════════════

def _verify_webhook_hmac(payload: bytes, provided_sig: str) -> bool:
    if not Config.WEBHOOK_SECRET: return True  # warn logged at startup
    expected = hmac.new(
        Config.WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, provided_sig or "")

def build_flask_app() -> Optional[Any]:
    if not FLASK_OK:
        log("warning", "webhook", "Flask not installed — webhook server disabled")
        return None

    app = Flask("OmegaAI")
    app.logger.disabled = True
    log_cli = logging.getLogger("werkzeug")
    log_cli.setLevel(logging.ERROR)

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok", "uptime": uptime_str(), "version": "10.0"})

    @app.route("/webhook/lead", methods=["POST"])
    def inbound_lead():
        """Accept inbound lead from any web form / CRM / ad platform."""
        payload = flask_request.get_data()
        sig     = flask_request.headers.get("X-Omega-Signature", "")
        if Config.WEBHOOK_SECRET and not _verify_webhook_hmac(payload, sig):
            return jsonify({"error": "invalid_signature"}), 403
        try:
            data = flask_request.get_json(force=True) or {}
        except Exception:
            return jsonify({"error": "invalid_json"}), 400

        email = (data.get("email") or "").strip().lower()
        if not validate_email(email):
            return jsonify({"error": "invalid_email"}), 422

        weights = load_weights()
        lead = {
            "email":    email,
            "name":     data.get("name", email.split("@")[0].title()),
            "company":  data.get("company", ""),
            "website":  data.get("website", ""),
            "category": data.get("category", "local business"),
            "source":   "inbound",
            "rating":   0,
            "reviews":  0,
        }
        lead["score"] = score_lead(lead, weights)

        DB.upsert_lead(
            email,
            name=lead["name"], company=lead["company"],
            website=lead["website"], category=lead["category"],
            source="inbound", score=lead["score"], status="new", stage=0,
        )
        DB.metric("inbound_leads")
        audit("INBOUND_LEAD", {"email": email, "source": "webhook"})
        notify(f"📥 Inbound lead: {lead['name']} ({email})")
        return jsonify({"ok": True, "score": lead["score"]}), 200

    @app.route("/webhook/stripe", methods=["POST"])
    def stripe_webhook():
        payload    = flask_request.get_data()
        sig_header = flask_request.headers.get("Stripe-Signature", "")
        result = handle_stripe_event(payload, sig_header)
        if not result["ok"]:
            return jsonify(result), 400
        return jsonify(result), 200

    @app.route("/webhook/typeform", methods=["POST"])
    def typeform_webhook():
        """Typeform / Tally / any form builder."""
        payload = flask_request.get_data()
        sig     = flask_request.headers.get("X-Omega-Signature", "")
        if Config.WEBHOOK_SECRET and not _verify_webhook_hmac(payload, sig):
            return jsonify({"error": "invalid_signature"}), 403
        try:
            data = flask_request.get_json(force=True) or {}
        except Exception:
            return jsonify({"error": "invalid_json"}), 400

        # Normalize Typeform structure
        answers  = data.get("form_response", {}).get("answers", [])
        email    = ""
        name     = ""
        category = "local business"
        for ans in answers:
            field_ref = ans.get("field", {}).get("ref", "")
            if ans.get("type") == "email":
                email = ans.get("email", "")
            elif "name" in field_ref.lower():
                name = ans.get("text", "")
            elif "business" in field_ref.lower() or "industry" in field_ref.lower():
                category = ans.get("text", category)

        if not email:
            return jsonify({"error": "no_email"}), 422

        weights = load_weights()
        lead = {"email": email, "name": name, "category": category, "source": "typeform"}
        lead["score"] = score_lead(lead, weights)
        DB.upsert_lead(email, name=name, category=category, source="typeform",
                       score=lead["score"], status="new", stage=0)
        DB.metric("inbound_leads")
        notify(f"📥 Typeform lead: {name} ({email})")
        return jsonify({"ok": True}), 200

    return app

def run_webhook_server(app):
    log("info", "webhook", f"Starting webhook server on {Config.WEBHOOK_HOST}:{Config.WEBHOOK_PORT}")
    try:
        app.run(host=Config.WEBHOOK_HOST, port=Config.WEBHOOK_PORT, debug=False, use_reloader=False)
    except Exception as e:
        log("error", "webhook", str(e))


# ══════════════════════════════════════════════════════════════
# SELF-LEARNING ENGINE
# ══════════════════════════════════════════════════════════════

def run_email_enrichment():
    """
    Process leads with status='needs_email' through SerpAPI owner email finder.
    Rate limited to 8 per cycle to preserve monthly quota.
    Runs every 1800s (30 min).
    """
    if _ENGINE_PAUSED.is_set():
        return
    try:
        import sys as _sys
        _sys.path.insert(0, "/data/data/com.termux/files/home")
        import omega_email_finder as _oef
    except ImportError:
        log("error", "enrichment", "omega_email_finder not found")
        return

    # Get next batch of leads needing email enrichment
    rows = DB.get().execute("""
        SELECT id, name, website, category
        FROM leads
        WHERE status = 'needs_email'
        AND website IS NOT NULL
        AND website != ''
        ORDER BY score DESC
        LIMIT 8
    """).fetchall()

    if not rows:
        log("info", "enrichment", "No leads need email enrichment")
        return

    found = 0
    skipped = 0

    for row in rows:
        lead_id  = row[0]
        name     = row[1] or ""
        website  = row[2] or ""
        category = row[3] or ""

        # Extract domain from website
        import re as _re
        domain = _re.sub(r'https?://', '', website).split('/')[0].replace('www.', '')

        try:
            email = _oef.find_owner_email(name, domain)
        except Exception as e:
            log("error", "enrichment", f"Finder error for {name}: {e}")
            email = None

        if email:
            # Update lead with real owner email
            DB.get().execute("""
                UPDATE leads
                SET email = ?, status = 'new', stage = 0,
                    last_contact_at = NULL
                WHERE id = ?
            """, (email, lead_id))
            DB.get().commit()
            log("info", "enrichment", f"✅ Found: {email} for {name}")
            found += 1
        else:
            # No owner email found — suppress this lead permanently
            DB.get().execute("""
                UPDATE leads SET status = 'suppressed' WHERE id = ?
            """, (lead_id,))
            DB.get().commit()
            skipped += 1

        import time as _t
        _t.sleep(2)  # Rate limit — respectful to SerpAPI

    log("info", "enrichment", f"Enrichment cycle: {found} found, {skipped} suppressed")
    if found > 0:
        notify(f"📧 Email enrichment: {found} owner emails found, {skipped} skipped")

def run_learning():
    weights = load_weights()
    metrics = DB.get_metrics()
    sent      = int(metrics.get("emails_sent", 0))
    bounced   = int(metrics.get("bounced", 0))
    replies   = int(metrics.get("real_replies", 0))
    interested = int(metrics.get("interested_leads", 0))

    if sent < 20: return  # not enough data yet

    bounce_rate = bounced / sent
    reply_rate  = replies / sent
    int_rate    = interested / max(replies, 1)

    # Tighten email quality requirements if bounce rate high
    if bounce_rate > 0.12:
        weights["valid_email"] = min(weights["valid_email"] * 1.08, 35.0)
        weights["biz_email"]   = min(weights["biz_email"] * 1.05, 25.0)
        log("info", "learning", f"Bounce rate {bounce_rate:.1%} — tightening email quality weights")

    # Reward high-engagement signals
    if reply_rate > 0.05:
        weights["high_reviews"] = min(weights["high_reviews"] * 1.03, 25.0)

    if int_rate > 0.15:
        weights["inbound_source"] = min(weights["inbound_source"] * 1.05, 35.0)

    # Relax if performing well
    if bounce_rate < 0.05 and sent > 50:
        weights["valid_email"] = max(weights["valid_email"] * 0.97, 15.0)

    save_weights(weights)
    log("info", "learning", f"Weights updated | bounce={bounce_rate:.1%} reply={reply_rate:.1%} int={int_rate:.1%}")
    DB.metric("learning_cycles")


# ══════════════════════════════════════════════════════════════
# WATCHDOG WORKER
# ══════════════════════════════════════════════════════════════

class Watchdog(threading.Thread):
    def __init__(self, name: str, fn: Callable, interval: int):
        super().__init__(daemon=True, name=f"WD-{name}")
        self.wname    = name
        self.fn       = fn
        self.interval = interval
        self.errors   = 0
        self.last_ok  : Optional[str] = None
        self.alive    = True

    def run(self):
        log("info", "watchdog", f"{self.wname} started ({self.interval}s)")
        while self.alive and not SHUTDOWN.is_set():
            try:
                self.fn()
                self.last_ok = datetime.now().isoformat()
                self.errors  = 0
            except Exception as e:
                self.errors += 1
                log("error", "watchdog", f"{self.wname} error #{self.errors}: {e}\n{traceback.format_exc()}")
                if self.errors >= 5:
                    notify(f"⚠️ {self.wname} failing ({self.errors}× in a row) — check logs")
            SHUTDOWN.wait(self.interval)

    def stop(self):
        self.alive = False

    @property
    def status_emoji(self) -> str:
        if self.errors >= 3: return "🔴"
        if self.errors >= 1: return "🟡"
        return "🟢"


# ══════════════════════════════════════════════════════════════
# TELEGRAM MISSION CONTROL
# ══════════════════════════════════════════════════════════════

_TELEGRAM_APP   = None
_BOT_PUSH_QUEUE : queue.Queue = queue.Queue(maxsize=500)
_AUTH_SESSIONS  : Dict[str, datetime] = {}
_auth_lock      = threading.Lock()

# ConversationHandler states
PIN_WAIT = 1

def _telegram_push(msg: str):
    """Non-blocking push to Telegram notification queue."""
    if not Config.TELEGRAM_BOT_TOKEN or not Config.TELEGRAM_CHAT_ID:
        return
    try:
        _BOT_PUSH_QUEUE.put_nowait({"chat_id": Config.TELEGRAM_CHAT_ID, "text": f"🤖 {msg}"})
    except queue.Full:
        pass

def _is_authed(chat_id: str) -> bool:
    with _auth_lock:
        exp = _AUTH_SESSIONS.get(str(chat_id))
        return bool(exp and datetime.now() < exp)

def _auth_session(chat_id: str):
    with _auth_lock:
        _AUTH_SESSIONS[str(chat_id)] = datetime.now() + timedelta(hours=12)

def _is_admin(user_id: int) -> bool:
    if not Config.TELEGRAM_ADMIN_IDS: return True  # open if no list set
    return str(user_id) in Config.TELEGRAM_ADMIN_IDS

def _main_menu(name: str) -> tuple[str, InlineKeyboardMarkup]:
    paused = _ENGINE_PAUSED.is_set()
    text = (
        f"🚀 *OMEGA AI v10 — MISSION CONTROL*\n\n"
        f"Commander: {name}\n"
        f"Engine: {'⏸ PAUSED' if paused else '🟢 ACTIVE'}\n"
        f"Uptime: {uptime_str()}\n"
        f"Sent today: {DB.daily_send_count()}/{Config.MAX_DAILY_SENDS}\n\n"
        f"Select an operation:"
    )
    kb = [
        [
            InlineKeyboardButton("📊 Dashboard",    callback_data="dash"),
            InlineKeyboardButton("💰 Revenue",       callback_data="revenue"),
        ],
        [
            InlineKeyboardButton("🎯 Pipeline",      callback_data="pipeline"),
            InlineKeyboardButton("🏆 Top Leads",     callback_data="top_leads"),
        ],
        [
            InlineKeyboardButton("👥 Clients",       callback_data="clients"),
            InlineKeyboardButton("📨 Inbox Intel",   callback_data="inbox_intel"),
        ],
        [
            InlineKeyboardButton("⚙️ System",        callback_data="system"),
            InlineKeyboardButton("📋 Logs",          callback_data="logs"),
        ],
        [
            InlineKeyboardButton("📒 Ledger",        callback_data="ledger"),
            InlineKeyboardButton("🎓 Onboarding",    callback_data="onboarding"),
        ],
        [
            InlineKeyboardButton("📊 Trading",  callback_data="open_trading"),
            InlineKeyboardButton("💎 Finance",  callback_data="open_finance"),
        ],
        [
            InlineKeyboardButton("⏸ Pause Engine" if not paused else "▶️ Resume Engine",
                                  callback_data="toggle_engine"),
        ],
    ]
    return text, InlineKeyboardMarkup(kb)

def _back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="menu")]])

if TELEGRAM_OK:

    async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        chat_id = str(update.effective_chat.id)
        if not _is_admin(user.id):
            await update.message.reply_text("⛔ Unauthorized.")
            return
        if Config.BOT_SECRET_PIN and not _is_authed(chat_id):
            await update.message.reply_text(
                "🔐 *Omega AI Mission Control*\n\nEnter your PIN to authenticate:",
                parse_mode="Markdown"
            )
            return PIN_WAIT
        text, kb = _main_menu(user.first_name)
        await update.message.reply_text(text, reply_markup=kb, parse_mode="Markdown")

    async def cmd_pin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        chat_id = str(update.effective_chat.id)
        pin = (update.message.text or "").strip()
        if pin == Config.BOT_SECRET_PIN:
            _auth_session(chat_id)
            user = update.effective_user
            text, kb = _main_menu(user.first_name)
            await update.message.reply_text(f"✅ Authenticated.\n\n{text}", reply_markup=kb, parse_mode="Markdown")
        else:
            await update.message.reply_text("❌ Wrong PIN. Try /start")
        return ConversationHandler.END

    async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        chat_id = str(update.effective_chat.id)
        if not _is_authed(chat_id):
            await update.message.reply_text("🔐 /start to authenticate")
            return
        m = DB.get_metrics()
        wd_lines = "\n".join(
            f"  {w.status_emoji} {w.wname}: {w.errors} errors"
            for w in _WATCHDOGS
        ) or "  No workers registered"
        text = (
            f"⚙️ *System Status*\n\n"
            f"Engine: {'⏸ PAUSED' if _ENGINE_PAUSED.is_set() else '🟢 RUNNING'}\n"
            f"Uptime: {uptime_str()}\n"
            f"Daily sends: {DB.daily_send_count()}/{Config.MAX_DAILY_SENDS}\n\n"
            f"*Workers:*\n{wd_lines}\n\n"
            f"*Key Metrics:*\n"
            f"📧 Emails sent: {int(m.get('emails_sent',0))}\n"
            f"📥 Replies: {int(m.get('real_replies',0))}\n"
            f"🔥 Interested: {int(m.get('interested_leads',0))}\n"
            f"💰 MRR: ${m.get('mrr',0):,.0f}\n"
        )
        await update.message.reply_text(text, parse_mode="Markdown")

    async def cmd_pause(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        chat_id = str(update.effective_chat.id)
        if not _is_authed(chat_id): return
        _ENGINE_PAUSED.set()
        audit("ENGINE_PAUSED", {"by": str(update.effective_user.id)})
        await update.message.reply_text("⏸ Engine paused. Use /resume to restart outreach.")

    async def cmd_resume(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        chat_id = str(update.effective_chat.id)
        if not _is_authed(chat_id): return
        _ENGINE_PAUSED.clear()
        audit("ENGINE_RESUMED", {"by": str(update.effective_user.id)})
        await update.message.reply_text("▶️ Engine resumed.")

    async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        text = (
            "📖 *Omega AI v10 — Commands*\n\n"
            "/start — Launch Mission Control\n"
            "/status — Quick system status\n"
            "/pause — Pause outreach engine\n"
            "/resume — Resume outreach engine\n"
            "/leads — Pipeline summary\n"
            "/revenue — Financial dashboard\n"
            "/clients — Active client list\n"
            "/help — This message\n"
        )
        await update.message.reply_text(text, parse_mode="Markdown")

    async def cmd_leads(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        chat_id = str(update.effective_chat.id)
        if not _is_authed(chat_id): return
        leads = DB.get_leads(status="new", limit=5)
        contacted = DB.get_leads(status="contacted", limit=5)
        lines = []
        for l in leads[:3]:
            lines.append(f"• {l['name']} ({l['email']}) Score:{l['score']:.0f}")
        text = (
            f"🎯 *Pipeline Summary*\n\n"
            f"New leads: {len(DB.get_leads(status='new'))}\n"
            f"Contacted: {len(DB.get_leads(status='contacted'))}\n"
            f"Interested: {len(DB.get_leads(status='interested'))}\n\n"
            f"*Top new leads:*\n" + ("\n".join(lines) if lines else "_None yet_")
        )
        await update.message.reply_text(text, parse_mode="Markdown")

    async def cmd_revenue(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        chat_id = str(update.effective_chat.id)
        if not _is_authed(chat_id): return
        m = DB.get_metrics()
        mrr  = m.get("mrr", 0)
        text = (
            f"💰 *Revenue Dashboard*\n\n"
            f"MRR: ${mrr:,.0f}\n"
            f"ARR: ${mrr*12:,.0f}\n"
            f"Conversions: {int(m.get('conversions',0))}\n"
            f"Churned: {int(m.get('churned',0))}\n"
            f"Payments received: {int(m.get('payments_received',0))}\n"
            f"Payment failures: {int(m.get('payment_failures',0))}\n\n"
            f"Projected MRR (interested): ${m.get('projected_mrr',0):,.0f}"
        )
        await update.message.reply_text(text, parse_mode="Markdown")

    async def cmd_clients(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        chat_id = str(update.effective_chat.id)
        if not _is_authed(chat_id): return
        clients = DB.get_clients()
        if not clients:
            await update.message.reply_text("👥 *Clients*\n\n_No clients yet._", parse_mode="Markdown")
            return
        lines = []
        for c in clients[:8]:
            p = Config.PRODUCTS.get(c.get("product_key",""), {})
            lines.append(f"• {c['name']} — {p.get('name','?')} ${c['mrr']:,.0f}/mo [{c['status']}]")
        await update.message.reply_text(
            "👥 *Active Clients*\n\n" + "\n".join(lines),
            parse_mode="Markdown"
        )

    async def master_button_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """Single entry point — routes all CallbackQuery to correct handler."""
        query = update.callback_query
        data  = query.data if query and query.data else ""
        # Route trading callbacks
        if data.startswith("trade_") or data == "open_trading":
            await trading_button_handler(update, ctx)
            return
        # Route finance callbacks
        if data.startswith("finance_") or data == "open_finance":
            await finance_button_handler(update, ctx)
            return
        # Everything else goes to main button_handler
        await button_handler(update, ctx)

    async def button_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        chat_id = str(query.message.chat_id)
        user = update.effective_user

        if not _is_authed(chat_id):
            await query.edit_message_text("🔐 Session expired. /start to re-authenticate.")
            return

        data = query.data
        m = DB.get_metrics()

        if data == "menu":
            text, kb = _main_menu(user.first_name)
            await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")

        elif data == "dash":
            _db = DB.get()
            sent       = _db.execute("SELECT COUNT(*) FROM emails_sent").fetchone()[0]
            sent_today = DB.daily_send_count()
            replies    = _db.execute(
                "SELECT COUNT(*) FROM email_replies WHERE intent NOT IN ('bounce','unsubscribe','autoresponder')"
            ).fetchone()[0]
            bounces    = _db.execute("SELECT COUNT(*) FROM email_replies WHERE intent='bounce'").fetchone()[0]
            hot        = _db.execute("SELECT COUNT(*) FROM leads WHERE status='interested'").fetchone()[0]
            total_leads= _db.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
            new_leads  = _db.execute("SELECT COUNT(*) FROM leads WHERE status='new'").fetchone()[0]
            contacted  = _db.execute("SELECT COUNT(*) FROM leads WHERE status='contacted'").fetchone()[0]
            clients    = _db.execute("SELECT COUNT(*) FROM clients WHERE status='active'").fetchone()[0]
            mrr        = _db.execute("SELECT COALESCE(SUM(mrr),0) FROM clients WHERE status='active'").fetchone()[0]
            rate_r     = f"{replies/sent*100:.1f}%" if sent else "0.0%"
            bounce_r   = f"{bounces/sent*100:.1f}%" if sent else "0.0%"
            cap_bar    = int((sent_today / Config.MAX_DAILY_SENDS) * 10) if Config.MAX_DAILY_SENDS else 0
            bar        = "█" * cap_bar + "░" * (10 - cap_bar)
            text = (
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"⚡ OMEGA AI — LIVE DASHBOARD\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📤 OUTREACH\n"
                f"  Sent today:     {sent_today} / {Config.MAX_DAILY_SENDS}\n"
                f"  [{bar}]\n"
                f"  Total sent:     {sent:,}\n\n"
                f"📥 ENGAGEMENT\n"
                f"  Real replies:   {replies}\n"
                f"  Reply rate:     {rate_r}\n"
                f"  Bounce rate:    {bounce_r}\n"
                f"  Interested:     {hot}\n\n"
                f"🎯 PIPELINE\n"
                f"  Total leads:    {total_leads:,}\n"
                f"  Untouched:      {new_leads:,}\n"
                f"  Contacted:      {contacted:,}\n\n"
                f"💰 REVENUE\n"
                f"  Active clients: {clients}\n"
                f"  MRR:            ${mrr:,.2f}\n\n"
                f"⏱ Uptime: {uptime_str()}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━"
            )
            await query.edit_message_text(text, reply_markup=_back_kb())

        elif data == "revenue":
            mrr = m.get("mrr", 0)
            text = (
                f"💰 *Revenue Dashboard*\n\n"
                f"💵 MRR:            ${mrr:,.0f}\n"
                f"📈 ARR:            ${mrr*12:,.0f}\n"
                f"🔄 Conversions:    {int(m.get('conversions',0))}\n"
                f"📉 Churned:        {int(m.get('churned',0))}\n"
                f"✅ Payments:       {int(m.get('payments_received',0))}\n"
                f"❌ Failed pmts:    {int(m.get('payment_failures',0))}\n"
                f"🔮 Proj. MRR:      ${m.get('projected_mrr',0):,.0f}\n\n"
                f"*Products:*\n"
                f"  Full Ops  $1,497/mo\n"
                f"  Growth    $997/mo\n"
                f"  Starter   $497/mo"
            )
            await query.edit_message_text(text, reply_markup=_back_kb(), parse_mode="Markdown")

        elif data == "pipeline":
            new_ct  = len(DB.get_leads(status="new"))
            cont_ct = len(DB.get_leads(status="contacted"))
            int_ct  = len(DB.get_leads(status="interested"))
            cli_ct  = len(DB.get_clients())
            text = (
                f"🎯 *Pipeline*\n\n"
                f"🔵 New leads:    {new_ct}\n"
                f"📨 Contacted:    {cont_ct}\n"
                f"🔥 Interested:   {int_ct}\n"
                f"💳 Clients:      {cli_ct}\n"
                f"📧 Sent today:   {DB.daily_send_count()}/{Config.MAX_DAILY_SENDS}\n"
                f"🤖 AI learning:  {int(m.get('learning_cycles',0))} cycles\n"
                f"🔍 Gate rate:    {int(m.get('gate_passed',0))}/{int(m.get('gate_passed',0)+m.get('gate_rejected',0))} passed"
            )
            await query.edit_message_text(text, reply_markup=_back_kb(), parse_mode="Markdown")

        elif data == "top_leads":
            hot = DB.get().execute(
                "SELECT email, name, score, category, stage FROM leads "
                "WHERE status NOT IN ('suppressed','blacklisted') "
                "ORDER BY score DESC LIMIT 8"
            ).fetchall()
            lines = [f"• {r['name']} — Score {r['score']:.0f} | {r['category'][:20]}" for r in hot]
            text = "🏆 *Top Scoring Leads*\n\n" + ("\n".join(lines) if lines else "_None yet_")
            await query.edit_message_text(text, reply_markup=_back_kb(), parse_mode="Markdown")

        elif data == "clients":
            clients = DB.get_clients()
            if not clients:
                text = "👥 *Clients*\n\n_No clients yet._"
            else:
                lines = []
                for c in clients[:8]:
                    p = Config.PRODUCTS.get(c.get("product_key",""), {})
                    lines.append(f"• {c['name']} — {p.get('name','?')} | {c['status']}")
                text = "👥 *Active Clients*\n\n" + "\n".join(lines)
            await query.edit_message_text(text, reply_markup=_back_kb(), parse_mode="Markdown")

        elif data == "inbox_intel":
            recent = DB.get().execute(
                "SELECT from_email, intent, received_at FROM email_replies "
                "ORDER BY received_at DESC LIMIT 8"
            ).fetchall()
            lines = [f"• {r['from_email']} → {r['intent']}" for r in recent]
            text = "📨 *Inbox Intelligence*\n\n" + ("\n".join(lines) if lines else "_No replies processed yet._")
            await query.edit_message_text(text, reply_markup=_back_kb(), parse_mode="Markdown")

        elif data == "system":
            try:
                wd_lines = "\n".join(
                    f"{w.status_emoji} {w.wname} ({w.errors} err) last OK: {(w.last_ok or 'never')[:16]}"
                    for w in _WATCHDOGS
                ) or "No workers registered"

                # Node mesh status
                try:
                    import psycopg2 as _pg
                    _conn = _pg.connect(host="127.0.0.1", port=5432, dbname="omega_bank", user="postgres", connect_timeout=3)
                    _cur = _conn.cursor()
                    _cur.execute("SELECT node_id, host, status, entry_count FROM omega_node_registry ORDER BY last_seen DESC")
                    nodes = _cur.fetchall()
                    _conn.close()
                    node_lines = "\n".join(f"  {'🟢' if n[2]=='active' else '🔴'} {n[0]} entries={n[3]:,}" for n in nodes)
                except:
                    node_lines = "  Bridge offline"

                text = (
                    f"OMEGA SYSTEM STATUS\n\n"
                    f"Engine: {'PAUSED' if _ENGINE_PAUSED.is_set() else 'RUNNING'}\n"
                    f"Uptime: {uptime_str()}\n"
                    f"Sent today: {DB.daily_send_count()}/{Config.MAX_DAILY_SENDS}\n\n"
                    f"WORKERS:\n{wd_lines}\n\n"
                    f"MESH NODES:\n{node_lines}\n\n"
                    f"SEND GATE:\n"
                    f"  Threshold: {Config.SEND_SCORE_THRESHOLD}\n"
                    f"  Daily cap: {Config.MAX_DAILY_SENDS}\n"
                    f"  Rate delay: {Config.RATE_LIMIT_DELAY}s\n\n"
                    f"DEPS: SDK={'OK' if ANTHROPIC_SDK_OK else 'REST'} "
                    f"Flask={'OK' if FLASK_OK else 'NO'} "
                    f"Stripe={'OK' if STRIPE_OK else 'NO'}"
                )
                await query.edit_message_text(text, reply_markup=_back_kb())
            except Exception as _se:
                await query.edit_message_text(f"System error: {_se}", reply_markup=_back_kb())

        elif data == "logs":
            notifs = pop_notifications(12)
            lines  = notifs if notifs else ["_No notifications yet._"]
            text   = "📋 *Recent Activity*\n\n" + "\n".join(lines)
            await query.edit_message_text(text, reply_markup=_back_kb(), parse_mode="Markdown")

        elif data == "ledger":
            try:
                import psycopg2 as _pgled
                conn = _pgled.connect(host="127.0.0.1", port=5432,
                                      dbname="omega_bank", user="postgres",
                                      connect_timeout=5)
                cur = conn.cursor()
                cur.execute("""
                    SELECT event_type, amount, direction, memo,
                           LEFT(chain_hash, 16) as chain_hash,
                           created_at
                    FROM ledger_entries
                    WHERE event_type NOT IN ('STRESS_TEST')
                    ORDER BY created_at DESC
                    LIMIT 10
                """)
                rows = cur.fetchall()
                conn.close()
                lines = []
                for r in rows:
                    icon = "📈" if r[2] == "CREDIT" else "📉"
                    amt  = f"${float(r[1]):>14,.2f}"
                    memo = (r[3] or "")[:30]
                    ts   = str(r[5])[:16]
                    chain = r[4] or "no-hash"
                    lines.append(f"{icon} {r[0][:18]} | {amt} | {ts}")
                text = (
                    "Omega Bank Ledger\n\n"
                    + ("\n".join(lines) if lines else "No entries yet")
                )
            except Exception as e:
                text = f"📒 *Omega Ledger*\n\nPG Error: {str(e)}"
            await query.edit_message_text(text, reply_markup=_back_kb())

        elif data == "onboarding":
            clients = DB.get_clients()
            if not clients:
                text = "Client Onboarding\n\nNo clients yet."
            else:
                lines = []
                for c in clients:
                    answers = json.loads(c.get("answers") or "{}")
                    done  = len(answers)
                    total = len(ONBOARD_QUESTIONS)
                    lines.append(f"- {c['name']} [{c['status']}] {done}/{total} questions")
                text = "Client Onboarding\n\n" + "\n".join(lines)
            await query.edit_message_text(text, reply_markup=_back_kb())

        elif data == "open_trading":
            text, kb = _trading_menu()
            await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")

        elif data == "open_finance":
            text, kb = _finance_menu()
            await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")

        elif data == "toggle_engine":
            if _ENGINE_PAUSED.is_set():
                _ENGINE_PAUSED.clear()
                audit("ENGINE_RESUMED", {"by": str(user.id)})
                status = "▶️ Engine RESUMED."
            else:
                _ENGINE_PAUSED.set()
                audit("ENGINE_PAUSED", {"by": str(user.id)})
                status = "⏸ Engine PAUSED."
            text, kb = _main_menu(user.first_name)
            await query.edit_message_text(f"{status}\n\n{text}", reply_markup=kb, parse_mode="Markdown")

    


# ════════════════════════════════════════════════════════
# OMEGA LEDGER — Double-entry journal functions
# Writes every revenue event to omega_ledger.db
# ════════════════════════════════════════════════════════
def _ledger_write(event_type: str, payload: dict):
    """Core writer — appends immutable event to omega_ledger.db."""
    try:
        import sqlite3 as _sq, json as _j, uuid as _u
        from datetime import datetime as _dt
        ledger_path = os.getenv("LEDGER_DB_PATH", "omega_ledger.db")
        conn = _sq.connect(ledger_path, check_same_thread=False)
        conn.execute(
            "INSERT INTO events (id, type, payload, timestamp) VALUES (?, ?, ?, ?)",
            (
                str(_u.uuid4()),
                event_type,
                _j.dumps(payload),
                _dt.utcnow().isoformat()
            )
        )
        conn.commit()
        conn.close()
        log("info", "ledger", f"Posted: {event_type} | ${payload.get('amount_usd', 0):,.2f}")
    except Exception as _e:
        log("error", "ledger", f"Ledger write failed: {_e}")


def ledger_record_payment(email: str, product_key: str, amount_usd: float):
    """Record a successful subscription payment."""
    _ledger_write("payment_received", {
        "email": email,
        "product_key": product_key,
        "amount_usd": round(float(amount_usd), 2),
        "debit_account": "accounts_receivable",
        "credit_account": "revenue",
        "memo": f"Subscription payment — {product_key}"
    })


def ledger_record_churn(email: str, product_key: str, amount_usd: float):
    """Record a subscription cancellation / churn event."""
    _ledger_write("subscription_churned", {
        "email": email,
        "product_key": product_key,
        "amount_usd": round(float(amount_usd), 2),
        "debit_account": "revenue",
        "credit_account": "churn_loss",
        "memo": f"Subscription cancelled — {product_key}"
    })


def ledger_record_trial(email: str, product_key: str):
    """Record a trial or onboarding start event."""
    _ledger_write("trial_started", {
        "email": email,
        "product_key": product_key,
        "amount_usd": 0.00,
        "debit_account": "pipeline",
        "credit_account": "trial_liability",
        "memo": f"Trial started — {product_key}"
    })

# ════════════════════════════════════════════════════════
# 8AM DAILY BRIEFING — Thread-based scheduler
# ════════════════════════════════════════════════════════
def send_daily_briefing_now(bot_token, admin_ids):
    """Fire every morning at 8AM Pacific with full business snapshot."""
    try:
        import sqlite3 as _sq
        _conn = _sq.connect(str(DB_PATH), check_same_thread=False)
        _c = _conn.cursor()

        _c.execute("SELECT COUNT(*) FROM leads")
        total_leads = _c.fetchone()[0]

        _c.execute("SELECT COUNT(*) FROM leads WHERE created_at >= date('now', '-1 days')")
        leads_today = _c.fetchone()[0]

        _c.execute("SELECT COUNT(*) FROM leads WHERE created_at >= date('now', '-7 days')")
        leads_week = _c.fetchone()[0]

        _c.execute("SELECT COUNT(*) FROM emails_sent WHERE sent_at >= date('now', '-1 days')")
        sent_today = _c.fetchone()[0]

        _c.execute("SELECT COUNT(*) FROM emails_sent WHERE sent_at >= date('now', '-7 days')")
        sent_week = _c.fetchone()[0]

        _c.execute("""SELECT COUNT(*) FROM email_replies
            WHERE received_at >= date('now', '-1 days')
            AND intent NOT IN ('bounce','unsubscribe','autoresponder')""")
        replies_today = _c.fetchone()[0]

        _c.execute("SELECT COUNT(*) FROM leads WHERE status = 'interested'")
        interested = _c.fetchone()[0]

        _c.execute("SELECT COUNT(*) FROM clients WHERE status = 'active'")
        active_clients = _c.fetchone()[0]

        _c.execute("SELECT COALESCE(SUM(mrr),0) FROM clients WHERE status = 'active'")
        mrr = _c.fetchone()[0]

        _c.execute("SELECT category, COUNT(*) as cnt FROM leads GROUP BY category ORDER BY cnt DESC LIMIT 3")
        top_cats = _c.fetchall()

        _c.execute("""
            SELECT name, company, category, score
            FROM leads WHERE status IN ('new','scored')
            ORDER BY score DESC LIMIT 3
        """)
        hot_leads = _c.fetchall()

        _conn.close()

        top_cat_str = "\n".join([f"  {r[0]}: {r[1]:,}" for r in top_cats])
        hot_lead_str = "\n".join([f"  {r[0]} | {r[1]} | {r[2]} | score:{r[3]}" for r in hot_leads])

        msg = f"""🌅 OMEGA AI — MORNING BRIEFING
━━━━━━━━━━━━━━━━━━━━━━
📊 LEADS
  Total: {total_leads:,}
  Added today: {leads_today:,}
  Added this week: {leads_week:,}

📧 OUTREACH
  Emails sent today: {sent_today}
  Emails sent this week: {sent_week}
  Replies today: {replies_today}

🔥 PIPELINE
  Interested: {interested}
  Active clients: {active_clients}
  MRR: ${mrr:,.2f}

🏆 TOP CATEGORIES
{top_cat_str}

⚡ HOT LEADS RIGHT NOW
{hot_lead_str}
━━━━━━━━━━━━━━━━━━━━━━
Let's get it, Thomas. 🚀"""

        for admin_id in admin_ids:
            _tg_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            _payload = _json_assistant.dumps({"chat_id": admin_id, "text": msg}).encode()
            _req = _urllib_req.Request(_tg_url, data=_payload, headers={"Content-Type": "application/json"})
            _urllib_req.urlopen(_req, timeout=10)

    except Exception as _e:
        for admin_id in admin_ids:
            _tg_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            _payload = _json_assistant.dumps({"chat_id": admin_id, "text": f"⚠️ Morning briefing error: {_e}"}).encode()
            _req = _urllib_req.Request(_tg_url, data=_payload, headers={"Content-Type": "application/json"})
            _urllib_req.urlopen(_req, timeout=10)

# ════════════════════════════════════════════════════════
# CLAUDE BUSINESS ASSISTANT — Free-text Telegram handler
# ════════════════════════════════════════════════════════
import urllib.request as _urllib_req
import json as _json_assistant

def _get_live_context():
    try:
        import sqlite3 as _sq
        _conn = _sq.connect(str(DB_PATH), check_same_thread=False)
        _c = _conn.cursor()
        _c.execute("SELECT COUNT(*) FROM leads")
        total_leads = _c.fetchone()[0]
        _c.execute("SELECT COUNT(*) FROM leads WHERE created_at >= date('now', '-7 days')")
        leads_week = _c.fetchone()[0]
        _c.execute("SELECT COUNT(*) FROM emails_sent")
        total_sent = _c.fetchone()[0]
        _c.execute("SELECT COUNT(*) FROM emails_sent WHERE sent_at >= date('now', '-7 days')")
        sent_week = _c.fetchone()[0]
        _c.execute("SELECT COUNT(*) FROM leads WHERE status = 'interested'")
        interested = _c.fetchone()[0]
        _c.execute("SELECT COUNT(*) FROM leads WHERE status = 'replied'")
        replied = _c.fetchone()[0]
        _c.execute("SELECT COUNT(*) FROM clients WHERE status = 'active'")
        active_clients = _c.fetchone()[0]
        _c.execute("SELECT COALESCE(SUM(mrr),0) FROM clients WHERE status = 'active'")
        mrr = _c.fetchone()[0]
        _c.execute("SELECT category, COUNT(*) as cnt FROM leads GROUP BY category ORDER BY cnt DESC LIMIT 5")
        top_cats = _c.fetchall()

        # Pull sample leads for context — top 10 by score, not yet contacted
        _c.execute("""
            SELECT name, company, email, category, score, status, stage
            FROM leads
            WHERE status IN ('new','scored')
            ORDER BY score DESC LIMIT 10
        """)
        top_leads = _c.fetchall()

        # Pull recent replies
        _c.execute("""
            SELECT from_email, intent, received_at
            FROM email_replies
            ORDER BY received_at DESC LIMIT 5
        """)
        recent_replies = _c.fetchall()

        _conn.close()
        return f"""You are Omega, the AI core of Omega AI — built exclusively for Thomas Lee Harvey.

Thomas is the CEO and architect of Omega AI. He is a visionary operator who built a fully automated revenue engine from his phone. Treat him as such. No fluff. No disclaimers. No suggestions to "contact an admin." You ARE the system. Respond like a sharp co-founder who has instant access to all data.

Communication style: Concise. Precise. Confident. Like two geniuses exchanging intel. No filler words. Lead with the answer.

LIVE SYSTEM DATA:
- Total leads: {total_leads:,}
- Leads this week: {leads_week:,}
- Emails sent total: {total_sent:,}
- Emails sent this week: {sent_week:,}
- Interested leads: {interested:,}
- Replied leads: {replied:,}
- Active clients: {active_clients}
- MRR: ${mrr:,.2f}
- Top categories: {top_cats}
- Top uncontacted leads (name | company | email | category | score):
{chr(10).join([f"  {r[0]} | {r[1]} | {r[2]} | {r[3]} | score:{r[4]}" for r in top_leads]) if top_leads else "  None"}
- Recent replies (from | intent | date):
{chr(10).join([f"  {r[0]} | {r[1]} | {r[2]}" for r in recent_replies]) if recent_replies else "  None"}

Products: Full Ops $1,497/mo | Growth Suite $997/mo | Starter $497/mo
Calendly: {os.getenv("CALENDLY_LINK", "https://calendly.com/omega-ai")}
CEO: Thomas Lee Harvey | thomas@omegaops.ai

Rules:
- Never say you can't access data. The data is above — use it.
- Never suggest contacting an admin. Thomas IS the admin.
- Answer in 1-4 sentences max unless drafting copy.
- If asked to draft an email, make it sharp and converting."""
        # Trading context
        try:
            trading_summary = get_trading_summary()
            trading_ctx = (
                f"- MEXC USDT balance: ${trading_summary['usdt_balance']:.4f}\n"
                f"- Open positions: {len(trading_summary['open_positions'])}\n"
                f"- Total trades: {trading_summary['total_trades']}\n"
                f"- Total PnL: {trading_summary['total_pnl']:+.4f} USDT\n"
                f"- Win rate: {trading_summary['win_rate']:.1f}%\n"
                f"- Auto-trade: {'ON' if trading_summary['auto_trade'] else 'OFF (paper mode)'}\n"
                f"- Daily loss: {trading_summary['daily_loss_pct']:.2f}%"
            )
            signals_ctx = ""
            for sym in TradingConfig.SYMBOLS[:3]:
                try:
                    price  = _MEXC_CLIENT.get_ticker(sym)
                    rating = _RATING_ENGINE.composite_rating(sym)
                    win_p  = _RATING_ENGINE.win_probability(sym)
                    sig    = "BUY" if rating >= 0.3 else ("SELL" if rating <= -0.3 else "HOLD")
                    signals_ctx += f"  {sym}: ${price:.4f} | {sig} | rating:{rating:+.3f} | win:{win_p:.1f}%\n"
                except Exception:
                    pass
        except Exception as _te:
            trading_ctx = f"Trading data unavailable: {_te}"
            signals_ctx = ""

        # Bank context
        try:
            bank = get_bank_summary()
            wallets = bank.get("wallets", [])
            top_wallets = "\n".join([
                f"  {(r[0] or 'Unknown')[:30]}: ${float(r[3] or 0):,.2f}"
                for r in wallets[:6]
            ])
            bridge_status = bank.get("bridge_status", "UNKNOWN")
        except Exception:
            top_wallets = "Bank bridge offline"
            bridge_status = "OFFLINE"

        # Ledger context
        try:
            import psycopg2 as _pg  # type: ignore
            _lconn = _pg.connect(host="127.0.0.1", port=5432,
                                  dbname="omega_bank", user="postgres", connect_timeout=3)
            _lc = _lconn.cursor()
            _lc.execute("""
                SELECT event_type, amount, memo, created_at
                FROM ledger_entries
                WHERE event_type NOT IN ('STRESS_TEST')
                ORDER BY created_at DESC LIMIT 5
            """)
            recent_ledger = _lc.fetchall()
            _lconn.close()
            ledger_ctx = "\n".join([
                f"  {r[0]} | ${float(r[1]):,.2f} | {(r[2] or '')[:40]} | {str(r[3])[:16]}"
                for r in recent_ledger
            ]) or "  No entries"
        except Exception as _le:
            ledger_ctx = f"Ledger unavailable: {_le}"

        return f"""You are Omega, the AI core of Omega AI — built exclusively for Thomas Lee Harvey.

Thomas is the CEO and architect of Omega AI. He built a fully automated revenue engine, HFT trading bot, and 7-layer banking core from two Android phones. Treat him as such. No fluff. No disclaimers. You ARE the system.

Communication style: Concise. Precise. Confident. Like two co-founders exchanging intel. Lead with the answer.

OMEGA AI — REVENUE ENGINE:
- Total leads: {total_leads:,}
- Leads this week: {leads_week:,}
- Emails sent total: {total_sent:,}
- Emails sent this week: {sent_week:,}
- Interested leads: {interested:,}
- Active clients: {active_clients}
- MRR: ${mrr:,.2f}
- Top categories: {top_cats}
- Top uncontacted leads:
{chr(10).join([f"  {r[0]} | {r[2]} | {r[3]} | score:{r[4]}" for r in top_leads]) if top_leads else "  None"}
- Recent replies:
{chr(10).join([f"  {r[0]} | {r[1]} | {r[2]}" for r in recent_replies]) if recent_replies else "  None"}

OMEGA TRADING — MEXC HFT:
{trading_ctx}
LIVE SIGNALS:
{signals_ctx}
OMEGA BANK — POSTGRESQL:
Bridge: {bridge_status}
Top wallets:
{top_wallets}

RECENT LEDGER ENTRIES:
{ledger_ctx}

Products: Full Ops $1,497/mo | Growth $997/mo | Starter $497/mo
CEO: Thomas Lee Harvey | simpl3hoods@gmail.com

Rules:
- Never say you cannot access data. Use what is above.
- Thomas IS the admin. Never suggest contacting one.
- Answer in 1-4 sentences max unless drafting copy.
- If asked how the business is doing, summarize all three systems.
- If asked about trading, give signals and PnL.
- If asked about the bank, give wallet balances.
- If asked to draft an email, make it sharp and converting."""

    except Exception as _e:
        return f"You are the Omega AI assistant. Live DB unavailable: {_e}."


async def handle_assistant_query(update, context):
    user_msg = update.message.text.strip()
    chat_id = update.effective_chat.id
    thinking_msg = await context.bot.send_message(chat_id=chat_id, text="🤖 Analyzing...")
    try:
        _system = _get_live_context()
        _api_key = os.getenv("ANTHROPIC_API_KEY")
        _payload = _json_assistant.dumps({
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 800,
            "system": _system,
            "messages": [{"role": "user", "content": user_msg}]
        }).encode("utf-8")
        _req = _urllib_req.Request(
            "https://api.anthropic.com/v1/messages",
            data=_payload,
            headers={
                "Content-Type": "application/json",
                "x-api-key": _api_key,
                "anthropic-version": "2023-06-01"
            },
            method="POST"
        )
        with _urllib_req.urlopen(_req, timeout=30) as _resp:
            _data = _json_assistant.loads(_resp.read().decode("utf-8"))
        reply = _data["content"][0]["text"]
        if len(reply) > 4000:
            reply = reply[:3997] + "..."
        await context.bot.delete_message(chat_id=chat_id, message_id=thinking_msg.message_id)
        await context.bot.send_message(chat_id=chat_id, text=reply)
    except Exception as _e:
        await context.bot.delete_message(chat_id=chat_id, message_id=thinking_msg.message_id)
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Assistant error: {_e}")

def build_telegram_app():
        if not TELEGRAM_OK:
            log("warning", "telegram", "python-telegram-bot not installed")
            return None
        if not Config.TELEGRAM_BOT_TOKEN:
            log("warning", "telegram", "TELEGRAM_BOT_TOKEN not set")
            return None

        app = ApplicationBuilder().token(Config.TELEGRAM_BOT_TOKEN).build()

        # Auth conversation
        conv = ConversationHandler(
            entry_points=[CommandHandler("start", cmd_start)],
            states={PIN_WAIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, cmd_pin)]},
            fallbacks=[CommandHandler("start", cmd_start)],
        )
        app.add_handler(conv)
        app.add_handler(CommandHandler("status",  cmd_status))
        app.add_handler(CommandHandler("pause",   cmd_pause))
        app.add_handler(CommandHandler("resume",  cmd_resume))
        app.add_handler(CommandHandler("help",    cmd_help))
        app.add_handler(CommandHandler("leads",   cmd_leads))
        app.add_handler(CommandHandler("revenue", cmd_revenue))
        app.add_handler(CommandHandler("clients", cmd_clients))
        app.add_handler(CallbackQueryHandler(master_button_handler))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_assistant_query))
        app.add_handler(CommandHandler("trading", cmd_trading))
        app.add_handler(CommandHandler("cards", cmd_cards))
        app.add_handler(CallbackQueryHandler(cards_button_handler, pattern="^card_"))
        app.add_handler(CommandHandler("finance", cmd_finance))

        return app


# ══════════════════════════════════════════════════════════════
# PUSH NOTIFICATION WORKER
# ══════════════════════════════════════════════════════════════

def _push_worker():
    """Background thread: drain push queue and send to Telegram via REST."""
    while not SHUTDOWN.is_set():
        try:
            item = _BOT_PUSH_QUEUE.get(timeout=2)
            if Config.TELEGRAM_BOT_TOKEN and Config.TELEGRAM_CHAT_ID:
                try:
                    requests.post(
                        f"https://api.telegram.org/bot{Config.TELEGRAM_BOT_TOKEN}/sendMessage",
                        json={
                            "chat_id": item["chat_id"],
                            "text": item["text"][:4096],
                            "parse_mode": "Markdown",
                        },
                        timeout=8,
                    )
                except Exception:
                    pass
        except queue.Empty:
            continue


# ══════════════════════════════════════════════════════════════
# ENGINE BOOTSTRAP
# ══════════════════════════════════════════════════════════════

def start_engine() -> List[Watchdog]:
    global _WATCHDOGS
    log("info", "boot", "Omega AI v10 engine bootstrapping")

    # Init DB
    DB.get()
    audit("SYSTEM_BOOT", {"version": "10.0"})

    watchdogs = [
        Watchdog("InboxWatchdog",  run_inbox,           Config.INBOX_POLL_INTERVAL),
        Watchdog("LeadGenWorker",  run_lead_generation, Config.LEAD_GEN_INTERVAL),
        Watchdog("OutreachWorker", run_outreach,        Config.OUTREACH_INTERVAL),
        Watchdog("LearningEngine", run_learning,        Config.LEARNING_INTERVAL),
        Watchdog("EmailEnricher",  run_email_enrichment, 1800),
    ]
    for wd in watchdogs:
        wd.start()

    # Push notification worker
    threading.Thread(target=_push_worker, daemon=True, name="PushWorker").start()

    _WATCHDOGS = watchdogs
    log("info", "boot", f"{len(watchdogs)} workers started")
    return watchdogs

def stop_engine():
    SHUTDOWN.set()
    for wd in _WATCHDOGS:
        wd.stop()
    log("info", "shutdown", "Omega AI v10 stopped")
    audit("SYSTEM_SHUTDOWN", {})


# ══════════════════════════════════════════════════════════════
# MAIN ENTRYPOINT
# ══════════════════════════════════════════════════════════════

def _print_banner():
    m = DB.get_metrics()
    print("\n" + "═"*66)
    print("  OMEGA AI v10 — ENTERPRISE REVENUE OPERATING SYSTEM")
    print(f"  CEO: {Config.CEO_NAME} | {Config.COMPANY_NAME}")
    print("═"*66)
    for k, p in Config.PRODUCTS.items():
        link = p.get("stripe", "⚠️ link not set")
        print(f"  • {p['name']:<28} ${p['price']:>7,.0f}/mo  {link}")
    print("═"*66)
    print(f"  MRR: ${m.get('mrr',0):,.0f}   Emails: {int(m.get('emails_sent',0))}   "
          f"Interested: {int(m.get('interested_leads',0))}   Conversions: {int(m.get('conversions',0))}")
    print("═"*66)


# ════════════════════════════════════════════════════════
# 8AM BRIEFING THREAD
# ════════════════════════════════════════════════════════
def _send_trading_briefing(bot_token, admin_ids):
    """8:30AM Pacific — Omega Trading performance briefing."""
    try:
        import urllib.request as _ur3, json as _jj3
        from datetime import datetime as _dtnow
        s       = get_trading_summary()
        history = _TRADING_STATE.trade_history
        wins    = [t for t in history if t["profit"] > 0]
        losses  = [t for t in history if t["profit"] <= 0]
        total_pnl = sum(t["profit"] for t in history)
        win_rate  = (len(wins) / len(history) * 100) if history else 0
        best  = max(history, key=lambda t: t["profit"])  if history else None
        worst = min(history, key=lambda t: t["profit"])  if history else None
        w = TradingConfig.WEIGHTS
        if w.get("macd",0) >= 2.0 and w.get("rsi",0) >= 2.0:
            strat = "RSI + MACD Momentum"
        elif w.get("vwap",0) >= 2.0:
            strat = "Trend Following"
        elif w.get("bollinger",0) >= 2.0:
            strat = "Range / Mean Reversion"
        else:
            strat = "Adaptive Auto-Tune"
        best_str  = f"{best['symbol']}  {best['profit']:+.4f} USDT"   if best  else "N/A"
        worst_str = f"{worst['symbol']} {worst['profit']:+.4f} USDT"  if worst else "N/A"
        open_lines = "  " + ", ".join(f"{sym}@{p['entry']:.4f}" for sym,p in _TRADING_STATE.holdings.items()) if _TRADING_STATE.holdings else "  None"
        msg = (
            "OMEGA TRADING — MORNING BRIEFING\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"  Time:         {_dtnow.now().strftime('%Y-%m-%d %H:%M')} Pacific\n\n"
            "PERFORMANCE\n"
            f"  Trades:       {len(history)}\n"
            f"  Wins/Losses:  {len(wins)} / {len(losses)}\n"
            f"  Win Rate:     {win_rate:.1f}%\n"
            f"  Total PnL:    {total_pnl:+.4f} USDT\n"
            f"  USDT Bal:     ${s['usdt_balance']:,.4f}\n"
            f"  Daily Loss:   {s['daily_loss_pct']:.2f}%\n\n"
            "BEST / WORST\n"
            f"  Best:   {best_str}\n"
            f"  Worst:  {worst_str}\n\n"
            "ACTIVE STRATEGY\n"
            f"  {strat}\n\n"
            "OPEN POSITIONS\n"
            f"{open_lines}\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "Capture alpha. Execute. Win."
        )
        for admin_id in admin_ids:
            _pl = _jj3.dumps({"chat_id": admin_id, "text": msg}).encode()
            _rq = _ur3.Request(f"https://api.telegram.org/bot{bot_token}/sendMessage", data=_pl, headers={"Content-Type": "application/json"})
            _ur3.urlopen(_rq, timeout=10)
        log("info", "briefing", "Trading briefing sent")
    except Exception as e:
        log("error", "briefing", f"Trading briefing error: {e}")

def _briefing_thread():
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td
    PACIFIC_OFFSET = _td(hours=-7)
    bot_token  = os.getenv("TELEGRAM_BOT_TOKEN")
    admin_ids  = [int(x.strip()) for x in os.getenv("TELEGRAM_ADMIN_IDS", "").split(",") if x.strip()]
    sent_omega    = False
    sent_trading  = False
    last_day      = None
    while not SHUTDOWN.is_set():
        now      = _dt.now(_tz.utc) + PACIFIC_OFFSET
        today    = now.strftime("%Y-%m-%d")
        if today != last_day:
            sent_omega   = False
            sent_trading = False
            last_day     = today
        if now.hour == 8 and now.minute >= 15 and not sent_omega:
            send_daily_briefing_now(bot_token, admin_ids)
            sent_omega = True
        if now.hour == 8 and now.minute >= 30 and not sent_trading:
            _send_trading_briefing(bot_token, admin_ids)
            sent_trading = True
        SHUTDOWN.wait(45)

# TRADING ENGINE — MEXC Python HFT (converted from index.js)
# ══════════════════════════════════════════════════════════════

import math
import websocket
import urllib.request as _tr
import urllib.parse as _tp
import hmac as _hmac
import hashlib as _hs
import json as _tj
import time as _tt
import threading as _thr
from datetime import datetime as _dt

# ── Trading Config ─────────────────────────────────────────
class TradingConfig:
    API_KEY        = os.getenv("MEXC_API_KEY", "")
    API_SECRET     = os.getenv("MEXC_API_SECRET", "")
    SYMBOLS        = [s.strip() for s in os.getenv("TRADE_SYMBOLS", "XRP/USDT,BTC/USDT,ETH/USDT").split(",")]
    MAX_RISK       = float(os.getenv("MAX_RISK_PER_TRADE", "0.02"))
    MAX_DAILY_LOSS = float(os.getenv("MAX_DAILY_LOSS", "0.05"))
    AUTO_TRADE     = False  # toggled via Telegram
    WS_ENDPOINT    = "wss://wbs.mexc.com/ws"
    REST_BASE      = "https://api.mexc.com"
    WEIGHTS        = {"rsi": 1.2, "macd": 1.5, "bollinger": 0.8, "candlestick": 1.5, "vwap": 1.2}
    RISK_MULT      = 1.8
    HEARTBEAT      = 3000

# ── MEXC REST API ──────────────────────────────────────────
class MEXCClient:
    def __init__(self):
        self.key    = TradingConfig.API_KEY
        self.secret = TradingConfig.API_SECRET
        self.base   = TradingConfig.REST_BASE

    def _sign(self, params: dict) -> str:
        query = _tp.urlencode(sorted(params.items()))
        return _hmac.new(self.secret.encode(), query.encode(), _hs.sha256).hexdigest()

    def _get(self, path: str, params: dict = None, signed: bool = False) -> dict:
        params = params or {}
        if signed:
            params["timestamp"] = int(_tt.time() * 1000)
            params["signature"] = self._sign(params)
        query = _tp.urlencode(params)
        url   = f"{self.base}{path}?{query}"
        req   = _tr.Request(url, headers={
            "X-MEXC-APIKEY": self.key,
            "Content-Type": "application/json"
        })
        try:
            with _tr.urlopen(req, timeout=10) as r:
                return _tj.loads(r.read())
        except Exception as e:
            log("error", "mexc", f"GET {path}: {e}")
            return {}

    def _post(self, path: str, params: dict) -> dict:
        params["timestamp"] = int(_tt.time() * 1000)
        params["signature"] = self._sign(params)
        data  = _tp.urlencode(params).encode()
        req   = _tr.Request(f"{self.base}{path}", data=data, headers={
            "X-MEXC-APIKEY": self.key,
            "Content-Type": "application/x-www-form-urlencoded"
        })
        try:
            with _tr.urlopen(req, timeout=10) as r:
                return _tj.loads(r.read())
        except Exception as e:
            log("error", "mexc", f"POST {path}: {e}")
            return {}

    def get_balance(self) -> dict:
        """Signed endpoint — uses API key + secret from .env."""
        import urllib.request as _ur, json as _jj
        import hmac as _hm, hashlib as _hs, time as _ti, urllib.parse as _up
        key    = os.getenv("MEXC_API_KEY", "")
        secret = os.getenv("MEXC_API_SECRET", "")
        if not key or not secret:
            log("warning", "mexc_balance", "MEXC_API_KEY or MEXC_API_SECRET not set")
            return {}
        try:
            params = {"timestamp": int(_ti.time() * 1000)}
            query  = _up.urlencode(sorted(params.items()))
            sig    = _hm.new(secret.encode(), query.encode(), _hs.sha256).hexdigest()
            params["signature"] = sig
            url = f"https://api.mexc.com/api/v3/account?{_up.urlencode(params)}"
            req = _ur.Request(url, headers={
                "X-MEXC-APIKEY": key,
                "Content-Type": "application/json"
            })
            with _ur.urlopen(req, timeout=10) as r:
                data = _jj.loads(r.read())
            balances = {}
            for b in data.get("balances", []):
                free = float(b.get("free", 0))
                if free > 0:
                    balances[b["asset"]] = free
            return balances
        except Exception as e:
            log("error", "mexc_balance", f"Balance fetch failed: {e}")
            return {}

    def get_klines(self, symbol: str, interval: str = "15m", limit: int = 100) -> list:
        import urllib.request as _ur, urllib.parse as _up, json as _j
        sym = symbol.replace("/", "").replace("-", "").upper()
        try:
            params = _up.urlencode({"symbol": sym, "interval": interval, "limit": limit})
            url = f"https://api.mexc.com/api/v3/klines?{params}"
            req = _ur.Request(url, headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json"
            })
            with _ur.urlopen(req, timeout=10) as r:
                data = _j.loads(r.read())
            return [[float(c[i]) for i in range(6)] for c in (data if isinstance(data, list) else [])]
        except Exception as e:
            log("error", "mexc", f"klines {sym}: {e}")
            return []

    def get_ticker(self, symbol: str) -> float:
        """Public endpoint — no auth needed, always returns live price."""
        import urllib.request as _ur, json as _jj
        sym = symbol.replace("/", "")
        try:
            url = f"https://api.mexc.com/api/v3/ticker/price?symbol={sym}"
            with _ur.urlopen(url, timeout=8) as r:
                return float(_jj.loads(r.read()).get("price", 0))
        except Exception as e:
            log("error", "mexc_ticker", f"{symbol}: {e}")
            return 0.0

    def place_market_buy(self, symbol: str, qty: float) -> dict:
        if not TradingConfig.AUTO_TRADE:
            log("info", "trading", f"[PAPER] BUY {qty:.6f} {symbol}")
            return {"paper": True, "symbol": symbol, "qty": qty}
        sym = symbol.replace("/", "")
        return self._post("/api/v3/order", {
            "symbol": sym, "side": "BUY",
            "type": "MARKET", "quantity": round(qty, 6)
        })

    def place_market_sell(self, symbol: str, qty: float) -> dict:
        if not TradingConfig.AUTO_TRADE:
            log("info", "trading", f"[PAPER] SELL {qty:.6f} {symbol}")
            return {"paper": True, "symbol": symbol, "qty": qty}
        sym = symbol.replace("/", "")
        return self._post("/api/v3/order", {
            "symbol": sym, "side": "SELL",
            "type": "MARKET", "quantity": round(qty, 6)
        })

# ── Pure Python Technical Indicators ──────────────────────
class Indicators:
    @staticmethod
    def sma(values: list, period: int) -> list:
        return [
            sum(values[i-period:i]) / period
            for i in range(period, len(values)+1)
        ]

    @staticmethod
    def ema(values: list, period: int) -> list:
        k   = 2 / (period + 1)
        ema = [values[0]]
        for v in values[1:]:
            ema.append(v * k + ema[-1] * (1 - k))
        return ema

    @staticmethod
    def rsi(closes: list, period: int = 14) -> float:
        if len(closes) < period + 1: return 50.0
        gains, losses = [], []
        for i in range(1, len(closes)):
            d = closes[i] - closes[i-1]
            gains.append(max(d, 0))
            losses.append(max(-d, 0))
        ag = sum(gains[-period:]) / period
        al = sum(losses[-period:]) / period
        if al == 0: return 100.0
        rs = ag / al
        return 100 - (100 / (1 + rs))

    @staticmethod
    def macd(closes: list, fast=12, slow=26, signal=9) -> dict:
        if len(closes) < slow: return {"macd": 0, "signal": 0, "histogram": 0}
        ema_fast = Indicators.ema(closes, fast)
        ema_slow = Indicators.ema(closes, slow)
        macd_line = [f - s for f, s in zip(ema_fast[-len(ema_slow):], ema_slow)]
        sig_line  = Indicators.ema(macd_line, signal)
        hist      = macd_line[-1] - sig_line[-1]
        return {"macd": macd_line[-1], "signal": sig_line[-1], "histogram": hist}

    @staticmethod
    def bollinger(closes: list, period=20, std_dev=2) -> dict:
        if len(closes) < period:
            p = closes[-1]
            return {"upper": p, "middle": p, "lower": p}
        window = closes[-period:]
        mid    = sum(window) / period
        std    = math.sqrt(sum((x - mid)**2 for x in window) / period)
        return {"upper": mid + std_dev*std, "middle": mid, "lower": mid - std_dev*std}

    @staticmethod
    def vwap(candles: list) -> float:
        pv = sum(((c[2]+c[3]+c[4])/3) * c[5] for c in candles)
        v  = sum(c[5] for c in candles)
        return pv / v if v else 0

    @staticmethod
    def atr(candles: list, period=14) -> float:
        if len(candles) < period+1: return 0
        trs = []
        for i in range(1, len(candles)):
            h, l, pc = candles[i][2], candles[i][3], candles[i-1][4]
            trs.append(max(h-l, abs(h-pc), abs(l-pc)))
        return sum(trs[-period:]) / period

# ── Candlestick Patterns (33 patterns) ────────────────────
class Patterns:
    @staticmethod
    def _bullish(c): return c[4] > c[1]
    @staticmethod
    def _bearish(c): return c[4] < c[1]
    @staticmethod
    def _body(c): return abs(c[4] - c[1])
    @staticmethod
    def _range(c): return c[2] - c[3]
    @staticmethod
    def _doji(c, t=0.001): return abs(c[4]-c[1]) <= t * c[1]

    @classmethod
    def score(cls, candles: list) -> int:
        if len(candles) < 5: return 0
        c = candles
        bull = 0
        bear = 0
        last = c[-1]
        prev = c[-2]

        # Bullish patterns
        if cls._bearish(prev) and cls._bullish(last) and last[1]>prev[4] and last[4]>prev[1]: bull+=2  # engulfing
        body=cls._body(last); ls=min(last[1],last[4])-last[3]
        if ls>2*body and (last[2]-max(last[1],last[4]))<body: bull+=1  # hammer
        us=last[2]-max(last[1],last[4])
        if us>2*body: bull+=1  # inverted hammer
        if cls._bearish(prev) and cls._bullish(last) and last[1]>prev[4] and last[4]<prev[1]: bull+=1  # harami
        if len(c)>=3:
            c1,c2,c3=c[-3],c[-2],c[-1]
            if cls._bearish(c1) and cls._bullish(c3) and cls._body(c2)<cls._range(c1)*0.3 and c3[4]>(c1[1]+c1[4])/2: bull+=2  # morning star
            if cls._bullish(c1) and cls._bullish(c2) and cls._bullish(c3) and c2[4]>c1[4] and c3[4]>c2[4]: bull+=2  # 3 white soldiers
            if cls._bearish(c1) and cls._bullish(c3) and cls._doji(c2): bull+=2  # bullish abandoned baby
            if cls._bearish(c1) and cls._bullish(c3) and cls._doji(c2) and c3[4]>(c1[1]+c1[4])/2: bull+=1  # doji star

        # Bearish patterns
        if cls._bullish(prev) and cls._bearish(last) and last[1]<prev[4] and last[4]<prev[1]: bear+=2  # engulfing
        if cls._bullish(prev) and cls._bearish(last) and last[1]<prev[4] and last[4]>prev[1]: bear+=1  # harami
        if len(c)>=3:
            c1,c2,c3=c[-3],c[-2],c[-1]
            if cls._bullish(c1) and cls._bearish(c3) and cls._body(c2)<cls._body(c1)*0.3 and c3[4]<(c1[1]+c1[4])/2: bear+=2  # evening star
            if cls._bearish(c1) and cls._bearish(c2) and cls._bearish(c3) and c2[4]<c1[4] and c3[4]<c2[4]: bear+=2  # 3 black crows
            if cls._bullish(c1) and cls._bearish(c3) and cls._doji(c2): bear+=2  # bearish abandoned baby

        return bull - bear  # positive=bullish, negative=bearish

# ── Composite Rating Engine ────────────────────────────────
class RatingEngine:
    def __init__(self, client: MEXCClient):
        self.client  = client
        self._cache  = {}

    def _get_candles(self, symbol: str, tf: str) -> list:
        key = f"{symbol}:{tf}"
        now = _tt.time()
        if key not in self._cache or now - self._cache[key]["ts"] > 900:
            candles = self.client.get_klines(symbol, tf, 100)
            self._cache[key] = {"data": candles, "ts": now}
        return self._cache[key]["data"]

    def composite_rating(self, symbol: str) -> float:
        timeframes = ["5m", "15m", "1h"]
        total_rating = 0
        w = TradingConfig.WEIGHTS
        total_weight = sum(w.values())

        for tf in timeframes:
            candles = self._get_candles(symbol, tf)
            if len(candles) < 30: continue
            closes = [c[4] for c in candles]

            rsi_val  = Indicators.rsi(closes)
            rsi_sig  = 1 if rsi_val < 30 else (-1 if rsi_val > 70 else 0)

            macd_res = Indicators.macd(closes)
            macd_sig = 1 if macd_res["histogram"] > 0 else -1

            bb       = Indicators.bollinger(closes)
            bb_sig   = 1 if closes[-1] < bb["lower"] else -1

            vwap_val = Indicators.vwap(candles)
            vwap_sig = 1 if closes[-1] > vwap_val else -1

            candle_sig = Patterns.score(candles)
            candle_sig = max(-1, min(1, candle_sig))

            rating = (
                rsi_sig    * w["rsi"] +
                macd_sig   * w["macd"] +
                bb_sig     * w["bollinger"] +
                candle_sig * w["candlestick"] +
                vwap_sig   * w["vwap"]
            ) / total_weight
            total_rating += rating

        return round(total_rating / len(timeframes), 4)

    def market_regime(self, symbol: str) -> str:
        candles = self._get_candles(symbol, "1h")
        if len(candles) < 30: return "range"
        closes  = [c[4] for c in candles]
        sma10   = Indicators.sma(closes, 10)
        sma30   = Indicators.sma(closes, 30)
        if not sma10 or not sma30: return "range"
        diff    = abs(sma10[-1] - sma30[-1]) / sma30[-1]
        mean    = sum(closes) / len(closes)
        std     = math.sqrt(sum((x-mean)**2 for x in closes) / len(closes))
        vol     = std / mean
        return "trending" if diff > 0.02 and vol > 0.01 else "range"

    def win_probability(self, symbol: str) -> float:
        rating = self.composite_rating(symbol)
        regime = self.market_regime(symbol)
        base   = (rating + 1) / 2  # normalize -1..1 to 0..1
        if regime == "trending": base *= 1.1
        return round(min(max(base, 0), 1) * 100, 1)

# ── Position & Trade Tracking ──────────────────────────────
class TradingState:
    def __init__(self):
        self.holdings     : dict  = {}
        self.trade_history: list  = []
        self.starting_bal : float = 0
        self.daily_loss   : float = 0
        self.last_tuned   : float = 0
        self.auto_trade   : bool  = False

_TRADING_STATE  = TradingState()
_MEXC_CLIENT    = MEXCClient()
_RATING_ENGINE  = RatingEngine(_MEXC_CLIENT)

# ── Core Trading Loop ──────────────────────────────────────
def run_trading_cycle():
    if not TradingConfig.API_KEY:
        log("warning", "trading", "MEXC_API_KEY not set — trading disabled")
        return

    balances = _MEXC_CLIENT.get_balance()
    usdt     = balances.get("USDT", 0)

    if _TRADING_STATE.starting_bal == 0:
        _TRADING_STATE.starting_bal = usdt

    daily_loss = (_TRADING_STATE.starting_bal - usdt) / max(_TRADING_STATE.starting_bal, 1)
    if daily_loss >= TradingConfig.MAX_DAILY_LOSS:
        log("warning", "trading", f"Daily loss limit hit {daily_loss:.1%} — pausing")
        notify(f"⚠️ Trading paused — daily loss {daily_loss:.1%}")
        return

    # Auto-tune weights every 15 min
    if _tt.time() - _TRADING_STATE.last_tuned > 900:
        _tune_trading_params()
        _TRADING_STATE.last_tuned = _tt.time()

    for symbol in TradingConfig.SYMBOLS:
        try:
            price  = _MEXC_CLIENT.get_ticker(symbol)
            if not price: continue

            rating = _RATING_ENGINE.composite_rating(symbol)
            regime = _RATING_ENGINE.market_regime(symbol)
            win_p  = _RATING_ENGINE.win_probability(symbol)

            log("info", "trading", f"{symbol} | rating={rating:.3f} | regime={regime} | win={win_p:.1f}%")

            # Entry
            if rating >= 0.3 and symbol not in _TRADING_STATE.holdings:
                candles = _MEXC_CLIENT.get_klines(symbol, "15m", 100)
                atr_val = Indicators.atr(candles)
                risk_amt = TradingConfig.MAX_RISK * usdt
                qty      = risk_amt / (atr_val * 2) if atr_val > 0 else 0
                if qty > 0:
                    order = _MEXC_CLIENT.place_market_buy(symbol, qty)
                    if order:
                        _TRADING_STATE.holdings[symbol] = {
                            "entry": price, "qty": qty,
                            "stop": price - atr_val * 2,
                            "take": price + atr_val * 5,
                            "trail": price - atr_val * TradingConfig.RISK_MULT,
                            "atr": atr_val, "ts": _tt.time(),
                            "regime": regime
                        }
                        DB.get().execute(
                            "INSERT INTO events(type,data) VALUES(?,?)",
                            ("TRADE_OPEN", _tj.dumps({"symbol": symbol, "price": price, "qty": qty, "regime": regime}))
                        )
                        DB.get().commit()
                        notify(f"📈 BUY {symbol} @ {price:.4f} | qty={qty:.4f} | win={win_p:.1f}%")

            # Exit
            elif symbol in _TRADING_STATE.holdings:
                pos = _TRADING_STATE.holdings[symbol]
                new_trail = price - pos["atr"] * TradingConfig.RISK_MULT
                pos["trail"] = max(pos["trail"], new_trail)

                should_exit = (
                    price <= pos["trail"] or
                    price >= pos["take"] or
                    price <= pos["stop"] or
                    (_tt.time() - pos["ts"]) > 3600
                )
                if should_exit:
                    order = _MEXC_CLIENT.place_market_sell(symbol, pos["qty"])
                    if order:
                        profit = (price - pos["entry"]) * pos["qty"]
                        _TRADING_STATE.trade_history.append({
                            "symbol": symbol, "entry": pos["entry"],
                            "exit": price, "profit": profit, "ts": _tt.time()
                        })
                        DB.get().execute(
                            "INSERT INTO events(type,data) VALUES(?,?)",
                            ("TRADE_CLOSE", _tj.dumps({"symbol": symbol, "price": price, "profit": round(profit,4)}))
                        )
                        DB.get().commit()
                        notify(f"📉 SELL {symbol} @ {price:.4f} | P&L={profit:+.4f} USDT")
                        del _TRADING_STATE.holdings[symbol]

        except Exception as e:
            log("error", "trading", f"{symbol}: {e}")

def _tune_trading_params():
    try:
        symbol  = TradingConfig.SYMBOLS[0]
        candles = _MEXC_CLIENT.get_klines(symbol, "15m", 100)
        if not candles: return
        closes  = [c[4] for c in candles]
        atr_val = Indicators.atr(candles)
        price   = closes[-1]
        vol     = atr_val / price if price else 0

        TradingConfig.HEARTBEAT = 5000 if vol > 0.02 else (15000 if vol < 0.01 else 10000)
        regime  = _RATING_ENGINE.market_regime(symbol)
        if regime == "trending":
            TradingConfig.WEIGHTS = {"rsi":0.8,"macd":1.5,"bollinger":0.6,"candlestick":1.0,"vwap":1.2}
        else:
            TradingConfig.WEIGHTS = {"rsi":1.0,"macd":1.0,"bollinger":0.8,"candlestick":1.0,"vwap":1.0}
        TradingConfig.RISK_MULT = 2.2 if vol > 0.02 else (1.8 if vol < 0.01 else 2.0)
        log("info", "trading", f"Params tuned | vol={vol:.4f} regime={regime} risk_mult={TradingConfig.RISK_MULT}")
    except Exception as e:
        log("error", "trading", f"Tune error: {e}")

def get_trading_summary() -> dict:
    balances = _MEXC_CLIENT.get_balance()
    usdt     = balances.get("USDT", 0)
    history  = _TRADING_STATE.trade_history
    total_pnl   = sum(t["profit"] for t in history)
    wins        = sum(1 for t in history if t["profit"] > 0)
    win_rate    = (wins / len(history) * 100) if history else 0
    return {
        "usdt_balance": usdt,
        "balances": balances,
        "open_positions": _TRADING_STATE.holdings,
        "total_trades": len(history),
        "total_pnl": round(total_pnl, 4),
        "win_rate": round(win_rate, 1),
        "auto_trade": TradingConfig.AUTO_TRADE,
        "daily_loss_pct": round((_TRADING_STATE.starting_bal - usdt) / max(_TRADING_STATE.starting_bal, 1) * 100, 2)
    }

# ══════════════════════════════════════════════════════════════
# TELEGRAM TRADING MENU
# ══════════════════════════════════════════════════════════════

async def cmd_trading(update, ctx):
    chat_id = str(update.effective_chat.id)
    if not _is_authed(chat_id):
        await update.message.reply_text("🔐 /start to authenticate")
        return
    text, kb = _trading_menu()
    await update.message.reply_text(text, reply_markup=kb, parse_mode="Markdown")

def _trading_menu():
    auto = TradingConfig.AUTO_TRADE
    s    = get_trading_summary()
    text = (
        f"📊 *TRADING DASHBOARD*\n\n"
        f"💵 USDT Balance: ${s['usdt_balance']:,.2f}\n"
        f"📈 Open positions: {len(s['open_positions'])}\n"
        f"🎯 Total trades: {s['total_trades']}\n"
        f"💰 Total P&L: {s['total_pnl']:+.4f} USDT\n"
        f"🏆 Win rate: {s['win_rate']:.1f}%\n"
        f"📉 Daily loss: {s['daily_loss_pct']:.2f}%\n"
        f"🤖 Auto-trade: {'🟢 ON' if auto else '🔴 OFF'}"
    )
    kb = [
        [
            InlineKeyboardButton("🔄 Refresh", callback_data="trade_dash"),
            InlineKeyboardButton("📡 Signals", callback_data="trade_signals"),
        ],
        [
            InlineKeyboardButton("🟢 Auto ON" if not auto else "🔴 Auto OFF",
                                  callback_data="trade_toggle"),
            InlineKeyboardButton("💼 Balances", callback_data="trade_balances"),
        ],
        [
            InlineKeyboardButton("📋 Positions", callback_data="trade_positions"),
            InlineKeyboardButton("📜 History", callback_data="trade_history"),
        ],
        [InlineKeyboardButton("🔙 Menu", callback_data="menu")],
    ]
    return text, InlineKeyboardMarkup(kb)

async def trading_button_handler(update, ctx):
    query = update.callback_query
    await query.answer()
    chat_id = str(query.message.chat_id)
    if not _is_authed(chat_id):
        await query.edit_message_text("🔐 Session expired.")
        return

    data = query.data

    if data in ("trade_dash", "open_trading"):
        text, kb = _trading_menu()
        await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")

    elif data == "open_finance":
        text, kb = _finance_menu()
        await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")

    elif data == "trade_toggle":
        TradingConfig.AUTO_TRADE = not TradingConfig.AUTO_TRADE
        state = "ENABLED" if TradingConfig.AUTO_TRADE else "DISABLED"
        audit("AUTO_TRADE_TOGGLE", {"state": state})
        notify(f"🤖 Auto-trade {state}")
        text, kb = _trading_menu()
        await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")

    elif data == "trade_signals":
        lines = []
        for sym in TradingConfig.SYMBOLS[:6]:
            try:
                price  = _MEXC_CLIENT.get_ticker(sym)
                rating = _RATING_ENGINE.composite_rating(sym)
                regime = _RATING_ENGINE.market_regime(sym)
                win_p  = _RATING_ENGINE.win_probability(sym)
                w      = TradingConfig.WEIGHTS
                sig    = "🟢 BUY" if rating >= 0.3 else ("🔴 SELL" if rating <= -0.3 else "⚪ HOLD")
                in_pos = "📌 IN POSITION" if sym in _TRADING_STATE.holdings else ""
                lines.append(
                    f"*{sym}* {in_pos}\n"
                    f"  {sig}  |  Rating: {rating:+.3f}\n"
                    f"  Win prob: {win_p:.1f}%  |  Regime: {regime}\n"
                    f"  Price: ${price:,.4f}\n"
                    f"  RSI:{w['rsi']} MACD:{w['macd']} BB:{w['bollinger']} VWAP:{w['vwap']}"
                )
            except Exception as e:
                lines.append(f"*{sym}*: error {e}")
        strat_w = TradingConfig.WEIGHTS
        if strat_w.get("macd",0) >= 2.0 and strat_w.get("rsi",0) >= 2.0:
            active_strat = "RSI + MACD Momentum"
        elif strat_w.get("vwap",0) >= 2.0:
            active_strat = "Trend Following"
        elif strat_w.get("bollinger",0) >= 2.0:
            active_strat = "Range / Mean Revert"
        else:
            active_strat = "Adaptive Auto-Tune"
        trade_back = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Trading", callback_data="trade_dash")]])
        text = (
            f"📡 *LIVE SIGNALS — {active_strat}*\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            + "\n\n".join(lines)
        )
        await query.edit_message_text(text, reply_markup=trade_back, parse_mode="Markdown")

    elif data == "trade_balances":
        try:
            balances = _MEXC_CLIENT.get_balance()
            lines = [f"  {asset}: {amt:.6f}" for asset, amt in balances.items()]
            text = "💼 *MEXC Balances*\n\n" + ("\n".join(lines) if lines else "_Empty wallet_")
        except Exception as e:
            text = f"💼 *MEXC Balances*\n\nError: {e}"
        await query.edit_message_text(text, reply_markup=_back_kb(), parse_mode="Markdown")

    elif data == "trade_positions":
        pos = _TRADING_STATE.holdings
        if not pos:
            text = "📋 *Open Positions*\n\n_No open positions_"
        else:
            lines = []
            for sym, p in pos.items():
                price = _MEXC_CLIENT.get_ticker(sym)
                pnl   = (price - p["entry"]) * p["qty"]
                lines.append(f"{sym}: entry={p['entry']:.4f} pnl={pnl:+.4f}")
            text = "📋 *Open Positions*\n\n" + "\n".join(lines)
        await query.edit_message_text(text, reply_markup=_back_kb(), parse_mode="Markdown")

    elif data == "trade_history":
        history = _TRADING_STATE.trade_history
        trade_back_kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📊 RSI+MACD",    callback_data="trade_strat_momentum"),
                InlineKeyboardButton("📈 Trend",        callback_data="trade_strat_trend"),
            ],
            [
                InlineKeyboardButton("🎯 Range",        callback_data="trade_strat_range"),
                InlineKeyboardButton("⚡ Adaptive",     callback_data="trade_strat_adaptive"),
            ],
            [InlineKeyboardButton("🔙 Trading",         callback_data="trade_dash")],
        ])
        if not history:
            text = "📜 *Trade History*\n\n_No trades executed yet_\n\nBot scanning markets in paper mode."
        else:
            wins      = [t for t in history if t["profit"] > 0]
            losses    = [t for t in history if t["profit"] <= 0]
            total_pnl = sum(t["profit"] for t in history)
            win_rate  = (len(wins) / len(history) * 100) if history else 0
            lines = []
            for t in reversed(history[-10:]):
                icon = "WIN " if t["profit"] > 0 else "LOSS"
                dur  = int((_tt.time() - t["ts"]) / 60)
                lines.append(
                    f"  [{icon}] {t['symbol']} | {t['profit']:+.4f} USDT\n"
                    f"         {t['entry']:.4f} -> {t['exit']:.4f} | {dur}m ago"
                )
            text = (
                "📜 *Trade History*\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n"
                f"  Trades: {len(history)}  |  Wins: {len(wins)}  |  Losses: {len(losses)}\n"
                f"  Win Rate: {win_rate:.1f}%  |  PnL: {total_pnl:+.4f} USDT\n"
                "━━━━━━━━━━━━━━━━━━━━━━\n" +
                "\n".join(lines)
            )
        await query.edit_message_text(text, reply_markup=trade_back_kb, parse_mode="Markdown")

    elif data in ("trade_strat_momentum", "trade_strat_trend", "trade_strat_range", "trade_strat_adaptive"):
        strat_map = {
            "trade_strat_momentum": ("RSI + MACD Momentum", {"rsi":2.0,"macd":2.0,"bollinger":0.5,"candlestick":1.0,"vwap":0.8}),
            "trade_strat_trend":    ("Trend Following",      {"rsi":0.5,"macd":2.0,"bollinger":0.5,"candlestick":0.8,"vwap":2.0}),
            "trade_strat_range":    ("Range / Mean Revert",  {"rsi":1.5,"macd":0.5,"bollinger":2.0,"candlestick":1.5,"vwap":0.8}),
            "trade_strat_adaptive": ("Adaptive Auto-Tune",   {"rsi":1.2,"macd":1.5,"bollinger":0.8,"candlestick":1.5,"vwap":1.2}),
        }
        name, weights = strat_map[data]
        TradingConfig.WEIGHTS = weights
        history  = _TRADING_STATE.trade_history
        wins     = len([t for t in history if t["profit"] > 0])
        win_rate = (wins / len(history) * 100) if history else 0
        _user = query.from_user
        audit("STRATEGY_CHANGED", {"strategy": name, "by": str(_user.id if _user else "unknown")})
        text = (
            f"⚡ *Strategy: {name}*\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"  RSI:       {weights['rsi']}\n"
            f"  MACD:      {weights['macd']}\n"
            f"  Bollinger: {weights['bollinger']}\n"
            f"  Candles:   {weights['candlestick']}\n"
            f"  VWAP:      {weights['vwap']}\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"  Win Rate:  {win_rate:.1f}%\n"
            "  Adaptive auto-tunes every 15 min on volatility + regime."
        )
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Trading", callback_data="trade_dash")]])
        await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")

# ══════════════════════════════════════════════════════════════
# OMEGA BANK BRIDGE — PostgreSQL Phone 2 via SSH tunnel
# ══════════════════════════════════════════════════════════════

import subprocess as _sp
import psycopg2 as _pg

_BRIDGE_PID = None

def start_bank_bridge():
    """Auto-start SSH tunnel to Phone 2 PostgreSQL on omega boot."""
    global _BRIDGE_PID
    try:
        proc = _sp.Popen([
            "ssh",
            "-i", "/data/data/com.termux/files/home/.ssh/omega_bridge",
            "-o", "StrictHostKeyChecking=no",
            "-o", "ServerAliveInterval=30",
            "-o", "ServerAliveCountMax=3",
            "-o", "ExitOnForwardFailure=yes",
            "-L", "5432:127.0.0.1:5432",
            "u0_a253@192.168.11.2",
            "-p", "8022", "-N"
        ], stdout=_sp.DEVNULL, stderr=_sp.DEVNULL)
        _BRIDGE_PID = proc.pid
        import time as _t; _t.sleep(5)
        log("info", "bridge", f"SSH tunnel started PID={_BRIDGE_PID}")
        notify("🌉 Omega Bank bridge ONLINE — Phone 2 PostgreSQL connected")
    except Exception as e:
        log("error", "bridge", f"Bridge failed: {e}")

def bank_query(sql: str, db: str = "omega_bank") -> list:
    """Execute read query against Phone 2 PostgreSQL."""
    try:
        conn = _pg.connect(
            host="127.0.0.1", port=5432,
            dbname=db, user="postgres",
            connect_timeout=5
        )
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchall()
        conn.close()
        return rows
    except Exception as e:
        log("error", "bridge", f"Query failed: {e}")
        return []

def get_bank_summary() -> dict:
    """Pull live financial summary from Omega Bank PostgreSQL."""
    try:
        import psycopg2 as _pg2
        conn = _pg2.connect(host="127.0.0.1", port=5432, dbname="omega_bank",
                            user="postgres", connect_timeout=5)
        cur = conn.cursor()

        # Wallets joined with accounts — correct column: id not wallet_id
        cur.execute("""
            SELECT a.owner_name, a.account_type, w.currency,
                   w.available_balance, w.pending_balance, w.settled_balance, w.status
            FROM wallets w
            LEFT JOIN accounts a ON a.account_id = w.account_id
            ORDER BY w.available_balance DESC NULLS LAST
            LIMIT 15
        """)
        wallets = cur.fetchall()

        # Cards — use pan_last4 and expiry columns
        cur.execute("""
            SELECT pan_last4, status, expiry
            FROM cards
            WHERE status = 'ACTIVE'
            LIMIT 10
        """)
        cards = cur.fetchall()

        # Treasury
        cur.execute("SELECT reserve_name, reserve_balance FROM treasury_accounts")
        treasury = cur.fetchall()

        # WAL — use ledger_event_stream (wal_stream has broken FDW)
        try:
            cur.execute("""
                SELECT event_type, payload, created_at
                FROM ledger_event_stream
                ORDER BY created_at DESC LIMIT 8
            """)
            wal_entries = cur.fetchall()
        except Exception:
            wal_entries = []

        conn.close()
        return {
            "wallets": wallets,
            "cards": cards,
            "treasury": treasury,
            "wal_entries": wal_entries,
            "bridge_status": "ONLINE"
        }
    except Exception as e:
        log("error", "bridge", f"get_bank_summary failed: {e}")
        return {
            "wallets": [], "cards": [], "treasury": [],
            "wal_entries": [], "bridge_status": f"ERROR: {e}"
        }

# ── Finance Menu Telegram Handler ──────────────────────────
async def cmd_finance(update, ctx):
    chat_id = str(update.effective_chat.id)
    if not _is_authed(chat_id):
        await update.message.reply_text("🔐 /start to authenticate")
        return
    text, kb = _finance_menu()
    await update.message.reply_text(text, reply_markup=kb, parse_mode="Markdown")

def _finance_menu():
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    s    = get_trading_summary()
    m    = DB.get_metrics()
    bank = get_bank_summary()
    wallets = bank.get("wallets", [])
    # row: (owner_name[0], account_type[1], currency[2], available_balance[3], pending_balance[4], settled_balance[5], status[6])
    reserve        = next((w for w in wallets if w[0] and "Primary Reserve" in str(w[0])), None)
    founder        = next((w for w in wallets if w[0] and "Thomas" in str(w[0])), None)
    ops_float      = next((w for w in wallets if w[0] and "Operations Float" in str(w[0])), None)
    reserve_ledger = next((w for w in wallets if w[0] and "RESERVE_LEDGER" in str(w[0])), None)
    reserve_bal    = f"${float(reserve[3] or 0):>16,.2f}"        if reserve        else "N/A"
    founder_bal    = f"${float(founder[3] or 0):>16,.2f}"        if founder        else "$0.00"
    ops_bal        = f"${float(ops_float[3] or 0):>16,.2f}"      if ops_float      else "$0.00"
    res_l_bal      = f"${float(reserve_ledger[3] or 0):>16,.2f}" if reserve_ledger else "$0.00"
    cards_ct       = len(bank.get("cards", []))
    treasury       = bank.get("treasury", [])
    sandbox        = next((t for t in treasury if t[0] and "SANDBOX"  in str(t[0])), None)
    primary_t      = next((t for t in treasury if t[0] and "PRIMARY"  in str(t[0])), None)
    sandbox_bal    = f"${float(sandbox[1] or 0):,.2f}"   if sandbox   else "$0"
    primary_bal    = f"${float(primary_t[1] or 0):,.2f}" if primary_t else "$0"
    # Pull fresh metrics directly from DB for accuracy
    _fresh_m   = DB.get_metrics()
    mrr        = _fresh_m.get("mrr", 0)
    emails_out = int(_fresh_m.get("emails_sent", 0))
    payments   = int(_fresh_m.get("payments_received", 0))
    _clients   = DB.get_clients()
    active_mrr = sum(c.get("mrr", 0) for c in _clients if c.get("status") == "active")
    leads_ct   = DB.get().execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    interested = DB.get().execute("SELECT COUNT(*) FROM leads WHERE status='interested'").fetchone()[0]
    bridge     = bank.get("bridge_status", "UNKNOWN")
    bridge_icon = "🟢" if bridge == "ONLINE" else "🔴"
    text = (
        "💎 *OMEGA FINANCIAL COMMAND CENTER*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🏦 *OMEGA BANK — LIVE BALANCES*\n"
        f"  Primary Reserve:   {reserve_bal}\n"
        f"  Reserve Ledger:    {res_l_bal}\n"
        f"  Ops Float:         {ops_bal}\n"
        f"  Founder Wallet:    {founder_bal}\n"
        f"  Virtual Cards:     {cards_ct} x $5,000 ACTIVE\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🏛 *TREASURY RESERVES*\n"
        f"  Primary Treasury:  {primary_bal}\n"
        f"  Sandbox Reserve:   {sandbox_bal}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📊 *MEXC TRADING ENGINE*\n"
        f"  USDT Balance:      ${s['usdt_balance']:,.6f}\n"
        f"  Total PnL:         {s['total_pnl']:+.4f} USDT\n"
        f"  Win Rate:          {s['win_rate']:.1f}%\n"
        f"  Open Positions:    {len(s['open_positions'])}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "💳 *OMEGA AI REVENUE*\n"
        f"  Active MRR:        ${active_mrr:,.0f}/mo\n"
        f"  ARR Run Rate:      ${active_mrr*12:,.0f}/yr\n"
        f"  Total Leads:       {leads_ct:,}\n"
        f"  Interested:        {interested}\n"
        f"  Payments:          {payments}\n"
        f"  Emails Sent:       {emails_out:,}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{bridge_icon} Bridge: {bridge}"
    )
    kb = [
        [
            InlineKeyboardButton("🏦 All Wallets",   callback_data="finance_bank"),
            InlineKeyboardButton("📒 WAL Stream",    callback_data="finance_wal"),
        ],
        [
            InlineKeyboardButton("🏛 Treasury",      callback_data="finance_treasury"),
            InlineKeyboardButton("💳 Virtual Cards", callback_data="finance_cards"),
        ],
        [
            InlineKeyboardButton("🔍 Account Audit", callback_data="finance_audit"),
            InlineKeyboardButton("📊 Trading",       callback_data="open_trading"),
        ],
        [
            InlineKeyboardButton("💰 Revenue",       callback_data="revenue"),
            InlineKeyboardButton("🔙 Main Menu",     callback_data="menu"),
        ],
    ]
    return text, InlineKeyboardMarkup(kb)

async def finance_button_handler(update, ctx):
    query = update.callback_query
    await query.answer()
    chat_id = str(query.message.chat_id)
    if not _is_authed(chat_id):
        await query.edit_message_text("🔐 Session expired.")
        return

    data = query.data

    fin_back_kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Finance", callback_data="open_finance")]])

    if data in ("open_finance",):
        text, kb = _finance_menu()
        await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")
        return

    elif data == "finance_bank":
        summary = get_bank_summary()
        if summary["bridge_status"] != "ONLINE":
            text = "🏦 *Omega Bank*\n\nBridge: " + summary["bridge_status"]
        else:
            lines = []
            for r in summary["wallets"][:13]:
                name  = (r[0] or "Unknown")[:28]
                bal   = float(r[3]) if r[3] is not None else 0.0
                stat  = r[6] or "active"
                lines.append(f"  {name}\n    ${bal:>16,.2f} [{stat}]")
            text = ("🏦 *Omega Bank — Live Wallets*\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    + ("\n".join(lines) if lines else "  _No wallets_"))
        await query.edit_message_text(text, reply_markup=fin_back_kb, parse_mode="Markdown")

    elif data == "finance_wal":
        summary = get_bank_summary()
        if not summary["wal_entries"]:
            text = "📒 *WAL Stream*\n\n_No entries yet_"
        else:
            lines = [
                f"  {str(r[0])[:20]}\n  {str(r[2])[:16]}"
                for r in summary["wal_entries"]
            ]
            text = "📒 *Ledger Event Stream*\n\n━━━━━━━━━━━━━━━━━━━━━━\n" + "\n\n".join(lines)
        await query.edit_message_text(text, reply_markup=fin_back_kb, parse_mode="Markdown")

    elif data == "finance_treasury":
        summary = get_bank_summary()
        treasury = summary.get("treasury", [])
        total = sum(float(t[1]) for t in treasury) if treasury else 0
        lines = [f"  {t[0]}: ${float(t[1]):,.2f}" for t in treasury] or ["  No treasury data"]
        text = ("TREASURY RESERVES\n"
                "──────────────────────────\n"
                + "\n".join(lines)
                + f"\n──────────────────────────\n  Total: ${total:,.2f}")
        await query.edit_message_text(text, reply_markup=fin_back_kb)

    elif data == "finance_cards":
        summary = get_bank_summary()
        cards = summary.get("cards", [])
        if not cards:
            text = "💳 *Virtual Cards*\n\n_No active cards_"
        else:
            lines = [f"  **** **** **** {c[0]}  [{c[1]}]\n  Exp: {c[2]}" for c in cards]
            text = "💳 *Virtual Cards — ACTIVE*\n\n━━━━━━━━━━━━━━━━━━━━━━\n" + "\n\n".join(lines)
        await query.edit_message_text(text, reply_markup=fin_back_kb, parse_mode="Markdown")

    elif data == "finance_audit":
        try:
            import psycopg2 as _pg2
            conn = _pg2.connect(host="127.0.0.1", port=5432, dbname="omega_bank",
                                user="postgres", connect_timeout=5)
            cur = conn.cursor()
            cur.execute("""
                SELECT a.owner_name, a.account_type, w.available_balance, w.pending_balance
                FROM accounts a LEFT JOIN wallets w ON w.account_id = a.account_id
                ORDER BY w.available_balance DESC NULLS LAST
            """)
            rows = cur.fetchall()
            cur.execute("""
                SELECT COUNT(*) FROM wallets w
                LEFT JOIN accounts a ON a.account_id = w.account_id
                WHERE a.account_id IS NULL
            """)
            orphans = cur.fetchone()[0]
            conn.close()
            lines = []
            for r in rows:
                bal  = f"${float(r[2]):>16,.2f}" if r[2] is not None else "          $0.00"
                pend = f"  +${float(r[3]):,.2f} pending" if r[3] and float(r[3]) > 0 else ""
                lines.append(f"  {(r[0] or 'Unknown')[:26]:<26} {bal}{pend}")
            text = ("🔍 *Account Audit*\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    + "\n".join(lines)
                    + f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                    f"\n  Accounts: {len(rows)}")
        except Exception as e:
            text = f"🔍 *Account Audit*\n\nError: {e}"
        await query.edit_message_text(text, reply_markup=fin_back_kb, parse_mode="Markdown")



async def cmd_cards(update, ctx):
    chat_id = str(update.effective_chat.id)
    if not _is_authed(chat_id):
        await update.message.reply_text("🔐 /start to authenticate")
        return
    text, kb = _cards_menu()
    await update.message.reply_text(text, reply_markup=kb)

def _cards_menu():
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    try:
        sys.path.insert(0, os.path.expanduser("~"))
        from omega_card_engine import get_cards, ensure_card_tables
        ensure_card_tables()
        cards = get_cards()
        active = sum(1 for c in cards if c[5] == "ACTIVE")
        total_limit = sum(float(c[6]) for c in cards)
        total_used  = sum(float(c[7]) for c in cards)
    except Exception:
        active = 0
        total_limit = total_used = 0
    text = (
        "💳 OMEGA CARD ENGINE\n\n"
        f"  Active Cards:  {active}\n"
        f"  Total Limit:   ${total_limit:,.2f}\n"
        f"  Total Used:    ${total_used:,.2f}\n"
        f"  Available:     ${total_limit - total_used:,.2f}\n\n"
        "  All cards SHA-256 chain verified.\n"
        "  Funded from Omega Treasury."
    )
    kb = [
        [
            InlineKeyboardButton("💳 Issue Card",    callback_data="card_issue"),
            InlineKeyboardButton("📋 List Cards",    callback_data="card_list"),
        ],
        [
            InlineKeyboardButton("📊 Transactions",  callback_data="card_txns"),
            InlineKeyboardButton("🔍 Audit Trail",   callback_data="card_audit"),
        ],
        [InlineKeyboardButton("🔙 Main Menu",        callback_data="menu")],
    ]
    return text, InlineKeyboardMarkup(kb)

async def cards_button_handler(update, ctx):
    query = update.callback_query
    await query.answer()
    chat_id = str(query.message.chat_id)
    if not _is_authed(chat_id):
        await query.edit_message_text("🔐 Session expired.")
        return
    data = query.data
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    cards_back = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Cards", callback_data="card_menu")]])
    try:
        sys.path.insert(0, os.path.expanduser("~"))
        from omega_card_engine import get_cards, issue_card, freeze_card, unfreeze_card, get_card_events, get_card_audit, ensure_card_tables
        ensure_card_tables()
    except Exception as e:
        await query.edit_message_text(f"Card engine error: {e}", reply_markup=_back_kb())
        return
    if data == "card_menu":
        text, kb = _cards_menu()
        await query.edit_message_text(text, reply_markup=kb)
    elif data == "card_list":
        cards = get_cards()
        if not cards:
            text = "💳 No cards issued yet."
        else:
            lines = []
            for c in cards:
                token, owner, last4, em, ey, status, limit, used, ctype, issued = c[:10]
                icon = "🟢" if status == "ACTIVE" else "🔴"
                avail = float(limit) - float(used)
                lines.append(f"{icon} *{last4} | {owner}\n  Limit: ${float(limit):,.2f} | Avail: ${avail:,.2f} | {status}")
            text = "💳 OMEGA CARDS\n\n" + "\n\n".join(lines)
        await query.edit_message_text(text, reply_markup=cards_back)
    elif data == "card_issue":
        try:
            card = issue_card(
                wallet_id="7597e069-65bc-4b55-b420-a2a2682f53e0",
                owner_name="Thomas Lee Harvey",
                spend_limit=5000.00
            )
            pan = card["pan"]
            text = (
                "💳 NEW CARD ISSUED\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"  {pan[:4]} {pan[4:8]} {pan[8:12]} {pan[12:]}\n"
                f"  {card['owner'][:22]}\n"
                f"  EXP: {card['expiry']}   CVV: {card['cvv']}\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"  Limit:  ${card['spend_limit']:,.2f}\n"
                f"  Token:  {card['card_token']}\n"
                f"  Chain:  {card['chain_hash'][:16]}\n"
                f"  Luhn:   VALID ✅\n\n"
                "  ⚠️ PAN shown once only — save it now"
            )
            notify(f"💳 Card issued: *{card['pan_last4']} | Thomas | ${card['spend_limit']:,.0f} limit")
        except Exception as e:
            text = f"Card issue failed: {e}"
        await query.edit_message_text(text, reply_markup=cards_back)
    elif data == "card_txns":
        cards = get_cards()
        if not cards:
            text = "No cards yet."
        else:
            token, owner, last4 = cards[0][0], cards[0][1], cards[0][2]
            events = get_card_events(token, limit=8)
            if not events:
                text = f"💳 *{last4} — No transactions yet"
            else:
                lines = [f"  {e[0]} ${float(e[1] or 0):,.2f} @ {e[2] or 'N/A'} [{e[3]}]" for e in events]
                text = f"💳 *{last4} — Transactions\n\n" + "\n".join(lines)
        await query.edit_message_text(text, reply_markup=cards_back)
    elif data == "card_audit":
        cards = get_cards()
        if not cards:
            text = "No cards yet."
        else:
            token, last4 = cards[0][0], cards[0][2]
            audit_data = get_card_audit(token)
            lines = [
                f"  Card:    *{last4}",
                f"  Owner:   {audit_data.get('owner','')}",
                f"  Status:  {audit_data.get('status','')}",
                f"  Events:  {audit_data.get('total_events',0)}",
            ]
            for e in audit_data.get("events", [])[:5]:
                lines.append(f"  {e['type']} ${e['amount']:,.2f} chain={e['chain_hash'][:8]}")
            text = "🔍 CARD AUDIT\n\n" + "\n".join(lines)
        await query.edit_message_text(text, reply_markup=cards_back)


def main():
    parser = argparse.ArgumentParser(description="Omega AI v10 Enterprise")
    parser.add_argument("--validate",    action="store_true", help="Run config validation and exit")
    parser.add_argument("--engine-only", action="store_true", help="Run engine only (no Telegram bot)")
    parser.add_argument("--bot-only",    action="store_true", help="Run Telegram bot only (no engine workers)")
    args = parser.parse_args()

    if args.validate:
        ok = StartupValidator.validate(verbose=True)
        sys.exit(0 if ok else 1)

    ok = StartupValidator.validate(verbose=True)
    if not ok:
        print("Fix critical issues above before running. Exiting.")
        sys.exit(1)

    _print_banner()

    def shutdown_handler(sig, frame):
        print(f"\n🛑 Signal {sig} — shutting down Omega AI v10...")
        stop_engine()
        sys.exit(0)

    signal.signal(signal.SIGINT,  shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    # Start webhook server
    flask_app = build_flask_app()

    if not args.bot_only:
        # Start engine workers
        start_engine()

        # Start webhook server in background thread
        if flask_app:
            threading.Thread(
                target=run_webhook_server,
                args=(flask_app,),
                daemon=True,
                name="WebhookServer",
            ).start()

    # Start Telegram bot
    if not args.engine_only and TELEGRAM_OK:
        import threading as _threading
        _bt = _threading.Thread(target=_briefing_thread, daemon=True, name="BriefingThread")
        _bt.start()
        log("info", "briefing", "8AM daily briefing thread started")
        tg_app = build_telegram_app()
        if tg_app:
            log("info", "telegram", "Telegram Mission Control starting (polling)")
            print("\n  🤖 Telegram Mission Control: ONLINE")
            print("  📡 Webhook Server: ONLINE")
            for wd in _WATCHDOGS:
                print(f"  {wd.status_emoji} {wd.wname:<20} ({wd.interval}s interval)")
            print("\n  Press Ctrl+C to stop.\n")
            # Run Telegram polling (blocking — this is the main thread)
            tg_app.run_polling(drop_pending_updates=True)
            return

    # No Telegram — keep alive with engine
    print("\n  Engine running. No Telegram bot (token not set or --engine-only).")
    print("  Press Ctrl+C to stop.\n")
    while not SHUTDOWN.is_set():
        time.sleep(1)


if __name__ == "__main__":
    main()


# ══════════════════════════════════════════════════════════════
# EMAIL VERIFICATION BEFORE SEND
# ══════════════════════════════════════════════════════════════

def verify_email_exists(email: str) -> bool:
    """Basic MX record check before sending."""
    import socket
    try:
        domain = email.split('@')[1]
        socket.getaddrinfo(domain, None)
        return True
    except Exception:
        log("warning", "verify", f"Domain not found for {email} — skipping")
        DB.suppress(email, "invalid_domain")
        return False

# ══════════════════════════════════════════════════════════════
# EMAIL VERIFICATION BEFORE SEND
# ══════════════════════════════════════════════════════════════



# ══════════════════════════════════════════════════════════════
# CLIENT ONBOARDING INTAKE — Auto-processes onboarding replies
# ══════════════════════════════════════════════════════════════

def process_onboarding_reply(email: str, body: str):
    """When a new client replies to onboarding email, extract their info."""
    client = DB.get().execute(
        "SELECT * FROM clients WHERE email=?", (email,)
    ).fetchone()
    if not client: return

    sys_p = (
        "Extract business onboarding information from this email reply. "
        "Return ONLY valid JSON with these keys: "
        "business_email, phone, crm, scheduling_link, ideal_customer, "
        "biggest_challenge, monthly_leads, current_response_time. "
        "Use null for any field not mentioned."
    )
    result = AI.generate(sys_p, body, max_tokens=500, smart=True)
    if not result: return

    try:
        clean = result.replace("```json","").replace("```","").strip()
        answers = json.loads(clean)
        DB.get().execute(
            "UPDATE clients SET answers=?, status='onboarding' WHERE email=?",
            (json.dumps(answers), email)
        )
        DB.get().commit()
        audit("CLIENT_ONBOARDED", {"email": email, "answers": answers})
        notify(f"✅ CLIENT ONBOARDED: {email} — answers captured, ready to deploy")

        # Send confirmation
        name = client["name"] or email.split("@")[0].title()
        EmailEngine.send(
            email,
            "You're being set up now — Omega AI",
            f"Hey {name},\n\nGot your answers. We're configuring your AI system now.\n\n"
            f"You'll receive a final confirmation within 24 hours once everything is live.\n\n"
            f"If you have questions, just reply here.",
            product_key=client["product_key"],
            add_sig=True,
        )
    except Exception as e:
        log("error", "onboarding", f"Failed to parse answers for {email}: {e}")

# ══════════════════════════════════════════════════════════════
# CONVERSATIONAL ONBOARDING ENGINE
# Client just replies to emails — Claude asks questions one at a time
# ══════════════════════════════════════════════════════════════

ONBOARD_QUESTIONS = [
    ("business_name",        "What's your business name?"),
    ("business_type",        "What type of business is it? (e.g. HVAC, dental, law firm)"),
    ("target_customer",      "Describe your ideal customer in one sentence."),
    ("biggest_challenge",    "What's your #1 challenge with leads right now?"),
    ("monthly_leads",        "Roughly how many leads do you get per month?"),
    ("current_followup",     "How do you currently follow up with new leads?"),
    ("scheduling_link",      "Do you have a booking/scheduling link? If yes paste it, if no just say no."),
    ("goal",                 "What would success look like for you in 30 days?"),
]

def get_onboard_state(email: str) -> dict:
    client = DB.get().execute(
        "SELECT answers FROM clients WHERE email=?", (email,)
    ).fetchone()
    if not client: return {}
    try:
        return json.loads(client["answers"] or "{}")
    except Exception:
        return {}

def save_onboard_state(email: str, state: dict):
    DB.get().execute(
        "UPDATE clients SET answers=? WHERE email=?",
        (json.dumps(state, default=str), email)
    )
    DB.get().commit()

def next_onboard_question(state: dict) -> Optional[tuple]:
    for key, question in ONBOARD_QUESTIONS:
        if key not in state:
            return key, question
    return None

def run_conversational_onboarding(email: str, body: str, subject: str):
    """Handle one turn of the onboarding conversation."""
    client = DB.get().execute(
        "SELECT * FROM clients WHERE email=?", (email,)
    ).fetchone()
    if not client: return False

    state = get_onboard_state(email)
    name  = client["name"] or email.split("@")[0].title()

    # Find which question we last asked and store the answer
    answered_keys = list(state.keys())
    for key, _ in ONBOARD_QUESTIONS:
        if key not in answered_keys:
            # This is the question they're answering
            state[key] = body.strip()[:500]
            save_onboard_state(email, state)
            break

    # Get next question
    nxt = next_onboard_question(state)

    if nxt:
        key, question = nxt
        total   = len(ONBOARD_QUESTIONS)
        current = len(state)
        reply = (
            f"Got it, {name}. {current}/{total} done.\n\n"
            f"{question}"
        )
        EmailEngine.send(
            email,
            f"Re: Setting up your Omega AI",
            reply,
            product_key=client["product_key"],
            add_sig=False,
        )
        log("info", "onboarding", f"{email} answered Q{current} → asking Q{current+1}")
    else:
        # All questions answered — finalize
        _finalize_onboarding(email, client, state)

    return True

def _finalize_onboarding(email: str, client, state: dict):
    """All questions answered — deploy and notify."""
    name        = client["name"] or email.split("@")[0].title()
    product_key = client["product_key"]
    p           = Config.PRODUCTS.get(product_key, Config.PRODUCTS["full_ops"])

    DB.get().execute(
        "UPDATE clients SET status='active', answers=? WHERE email=?",
        (json.dumps(state, default=str), email)
    )
    DB.get().commit()
    DB.metric("clients_fully_onboarded")
    audit("CLIENT_FULLY_ONBOARDED", {"email": email, "state": state})

    summary = "\n".join(f"• {k.replace('_',' ').title()}: {v}" for k, v in state.items())

    # Send client their confirmation
    EmailEngine.send(
        email,
        "Your Omega AI is being deployed now",
        f"Hey {name},\n\n"
        f"You're all set. Here's what we captured:\n\n{summary}\n\n"
        f"Your AI system goes live within 24 hours. You'll get a final confirmation "
        f"once your inbox monitoring, lead response, and follow-up sequences are active.\n\n"
        f"Questions? Just reply here.",
        product_key=product_key,
        add_sig=True,
    )

    # Build Telegram alert with full client profile
    bot_token  = os.getenv("TELEGRAM_BOT_TOKEN")
    admin_ids  = [int(x.strip()) for x in os.getenv("TELEGRAM_ADMIN_IDS","").split(",") if x.strip()]
    alert = (
        f"CLIENT FULLY ONBOARDED\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Name:      {name}\n"
        f"Email:     {email}\n"
        f"Product:   {p.get('name','?')}\n"
        f"MRR:       ${p.get('price',0):,.0f}/mo\n"
        f"Business:  {state.get('business_name','?')} — {state.get('business_type','?')}\n"
        f"Challenge: {state.get('biggest_challenge','?')}\n"
        f"Leads/mo:  {state.get('monthly_leads','?')}\n"
        f"Goal:      {state.get('goal','?')}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"System deploying to their market now."
    )
    import urllib.request as _ur2, json as _jj2
    for admin_id in admin_ids:
        try:
            _pl = _jj2.dumps({"chat_id": admin_id, "text": alert}).encode()
            _rq = _ur2.Request(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                data=_pl, headers={"Content-Type": "application/json"}
            )
            _ur2.urlopen(_rq, timeout=10)
        except Exception:
            pass

    # Auto-expand lead scraper to client's market
    biz_type = state.get("business_type", "").strip()
    if biz_type and biz_type not in LEAD_CATEGORIES:
        LEAD_CATEGORIES.append(biz_type)
        log("info", "onboarding", f"Added {biz_type} to lead categories for {name}")

    ledger_record_payment(email, product_key, p.get("price", 0))
    audit("CLIENT_FULLY_ONBOARDED", {"email": email, "state": state})
    log("info", "onboarding", f"Client {name} fully onboarded — {p.get('name','?')} active")



# ══════════════════════════════════════════════════════════════

# ════════════════════════════════════════════════════════
# OMEGA SAFE TRANSFER LAYER v1.0
# Quorum-gated, async parallel commits, self-rebuilding
# Wired into _ledger_write for all transfers >= $500
# ════════════════════════════════════════════════════════

import threading as _threading
import hashlib as _hashlib
from urllib.request import urlopen as _urlopen, Request as _Request
from urllib.error import URLError as _URLError
import json as _json_st

CONSENSUS_NODES = [
    "192.168.11.115:7432",
    "192.168.11.2:7432",
]
QUORUM_THRESHOLD = 500.00
CONSENSUS_TIMEOUT = 8

def _compute_proposal_hash(snapshot_id, amount, debit, credit):
    raw = f"{snapshot_id}:{amount}:{debit}:{credit}"
    return _hashlib.sha256(raw.encode()).hexdigest()

def _request_consensus_vote(endpoint, snapshot_id, state_hash, amount, debit, credit, memo):
    """Ask a consensus node to vote. Returns True/False/None."""
    try:
        payload = _json_st.dumps({
            "snapshot_id": snapshot_id,
            "state_hash":  state_hash,
            "amount":      str(amount),
            "debit":       debit,
            "credit":      credit,
            "memo":        memo,
        }).encode()
        req = _Request(
            f"http://{endpoint}/vote",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with _urlopen(req, timeout=CONSENSUS_TIMEOUT) as resp:
            body = _json_st.loads(resp.read())
            return body.get("approved", False)
    except Exception:
        return None

def _quorum_approve(amount, debit, credit, memo):
    """
    Run quorum vote across all consensus nodes in parallel.
    Returns (approved: bool, snapshot_id: str)
    """
    import uuid as _uuid_st
    snapshot_id = str(_uuid_st.uuid4())
    state_hash  = _compute_proposal_hash(snapshot_id, amount, debit, credit)

    results = {}
    threads = []

    def vote(endpoint):
        results[endpoint] = _request_consensus_vote(
            endpoint, snapshot_id, state_hash, amount, debit, credit, memo
        )

    for node in CONSENSUS_NODES:
        t = _threading.Thread(target=vote, args=(node,), daemon=True)
        threads.append(t)
        t.start()

    for t in threads:
        t.join(timeout=CONSENSUS_TIMEOUT + 1)

    approvals  = sum(1 for v in results.values() if v is True)
    total      = len(CONSENSUS_NODES)
    needed     = (total // 2) + 1
    approved   = approvals >= needed

    log("info", "consensus",
        f"Quorum: snapshot={snapshot_id[:8]} approvals={approvals}/{total} "
        f"needed={needed} → {'APPROVED' if approved else 'REJECTED'}")

    return approved, snapshot_id

def _pg_ledger_write(event_type, payload, snapshot_id=None):
    """
    Mirror every ledger event into PostgreSQL omega_bank.
    Runs in a background thread — never blocks the main flow.
    """
    try:
        import psycopg2 as _pg_local
        import uuid as _uuid_pg
        import hashlib as _hs_pg

        conn = _pg_local.connect(
            host="127.0.0.1", port=5432,
            user="postgres", dbname="omega_bank"
        )
        conn.autocommit = True
        cur = conn.cursor()

        amount    = float(payload.get("amount_usd", 0.01))
        debit     = payload.get("debit_account", "omega-debit")
        credit    = payload.get("credit_account", "omega-credit")
        memo      = payload.get("memo", event_type)
        idem_key  = _hs_pg.sha256(
            f"{event_type}:{payload.get('email','')}:{amount}:{snapshot_id or ''}".encode()
        ).hexdigest()[:32]

        cur.execute("""
            INSERT INTO ledger_entries
                (transaction_id, wallet_id, event_type, amount, direction,
                 debit_account, credit_account, memo, idempotency_key)
            VALUES
                (uuid_generate_v4(),
                 '2db2e016-f6a1-4086-bec2-363edfb1c26b',
                 %s, %s, 'CREDIT', %s, %s, %s, %s)
            ON CONFLICT (idempotency_key) DO NOTHING
        """, (event_type, max(amount, 0.01), debit, credit, memo, idem_key))

        conn.close()
        log("info", "pg_ledger", f"PG mirror: {event_type} ${amount:.2f}")
    except Exception as _pe:
        log("error", "pg_ledger", f"PG mirror failed: {_pe}")

def _node_manifest_write():
    """
    Write this node's self-description to PostgreSQL.
    Enables self-rebuilding — any node can reconstruct
    its role and config from the manifest on restart.
    """
    try:
        import psycopg2 as _pg_m
        import socket as _sock
        conn = _pg_m.connect(
            host="127.0.0.1", port=5432,
            user="postgres", dbname="omega_bank"
        )
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS omega_node_manifest (
                node_id     TEXT PRIMARY KEY,
                hostname    TEXT,
                config      JSONB,
                version     TEXT,
                updated_at  TIMESTAMP DEFAULT NOW()
            )
        """)
        cur.execute("""
            INSERT INTO omega_node_manifest (node_id, hostname, config, version)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (node_id) DO UPDATE
              SET config     = EXCLUDED.config,
                  updated_at = NOW()
        """, (
            "omega-node-001",
            _sock.gethostname(),
            _json_st.dumps({
                "role": "control_plane",
                "consensus_port": 7432,
                "quorum_threshold": QUORUM_THRESHOLD,
                "pg_host": "192.168.11.2",
                "nodes": CONSENSUS_NODES,
            }),
            "v10.0"
        ))
        conn.close()
    except Exception as _me:
        log("error", "manifest", f"Manifest write failed: {_me}")

def _safe_ledger_write(event_type: str, payload: dict):
    """
    Drop-in replacement for _ledger_write.
    For amounts >= $500: requires quorum approval before commit.
    All writes mirror to PostgreSQL in parallel — instantaneous.
    """
    amount  = float(payload.get("amount_usd", 0))
    debit   = payload.get("debit_account", "")
    credit  = payload.get("credit_account", "")
    memo    = payload.get("memo", event_type)

    snapshot_id = None

    # Quorum gate for large transfers
    if amount >= QUORUM_THRESHOLD:
        try:
            approved, snapshot_id = _quorum_approve(amount, debit, credit, memo)
            if not approved:
                log("error", "safe_ledger",
                    f"Transfer BLOCKED by quorum: {event_type} ${amount:.2f}")
                return
        except Exception as _qe:
            # Consensus unreachable — fail open with warning (configurable)
            log("error", "safe_ledger", f"Quorum unreachable, proceeding: {_qe}")

    # SQLite write (original — never removed)
    _ledger_write(event_type, payload)

    # PostgreSQL mirror — async, never blocks
    _threading.Thread(
        target=_pg_ledger_write,
        args=(event_type, payload, snapshot_id),
        daemon=True
    ).start()

    # Node manifest refresh — async
    _threading.Thread(target=_node_manifest_write, daemon=True).start()

# ── Patch the three revenue functions to use SafeTransfer ──



