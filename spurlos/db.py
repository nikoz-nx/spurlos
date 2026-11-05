"""SQLite-Speicher: Einstellungen, Firmen, Anfragen, Nachrichten, Verlauf."""
from __future__ import annotations

import copy
import json
import sqlite3
import threading
from datetime import datetime
from typing import Any

from . import config

_LOCK = threading.RLock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS brokers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT,
    origin TEXT,              -- datenanfragen | incogni | eigene
    region TEXT,
    lang TEXT DEFAULT 'de',
    email TEXT,
    webform TEXT,
    webform_only INTEGER DEFAULT 0,
    address TEXT,
    website TEXT,
    needs_id INTEGER DEFAULT 0,
    transport TEXT,
    source_url TEXT,
    notes TEXT,
    is_new INTEGER DEFAULT 0,
    active INTEGER DEFAULT 1,
    user_edited INTEGER DEFAULT 0,
    grp TEXT,                 -- consumer | b2b | adtech | people | credit | us
    countries TEXT,           -- z. B. "de" oder "eu" oder "all"
    what TEXT,                -- kurze Beschreibung
    confirmed INTEGER DEFAULT 0,
    added_at TEXT
);
CREATE TABLE IF NOT EXISTS requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ref TEXT UNIQUE,
    broker_id TEXT NOT NULL REFERENCES brokers(id),
    status TEXT NOT NULL,
    label TEXT,
    outcome TEXT,
    channel TEXT,
    planned_for TEXT,
    sent_at TEXT,
    due_at TEXT,
    reminder_sent_at TEXT,
    reminder_due_at TEXT,
    closed_at TEXT,
    last_message_id TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id INTEGER REFERENCES requests(id),
    direction TEXT NOT NULL,     -- out | in
    kind TEXT,                   -- request | reminder | followup | reply | auto | bounce | test
    message_id TEXT,
    in_reply_to TEXT,
    from_addr TEXT,
    to_addr TEXT,
    subject TEXT,
    date TEXT,
    body TEXT,
    attachments TEXT,
    category TEXT,
    confidence REAL,
    rule TEXT,
    match_text TEXT,
    ai_category TEXT,
    ai_note TEXT,
    reviewed INTEGER DEFAULT 0,
    imap_uid TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id INTEGER,
    at TEXT NOT NULL,
    kind TEXT,
    text TEXT
);
CREATE INDEX IF NOT EXISTS idx_requests_status ON requests(status);
CREATE INDEX IF NOT EXISTS idx_messages_request ON messages(request_id);
CREATE INDEX IF NOT EXISTS idx_events_request ON events(request_id);
"""

DEFAULTS: dict[str, Any] = {
    "profile": {
        "first_name": "",
        "last_name": "",
        "former_names": [],
        "addresses": [],     # {"text": "...", "current": bool, "note": "bis 10/2026"}
        "emails": [],        # {"address": "...", "main": bool, "retiring": bool}
        "phones": [],        # {"number": "...", "label": "Mobil"}
        "companies": [],     # {"name": "Firma"} – nur eigene Firmen (Selbstständige)
        "websites": [],      # {"url": "meinname.de"}
    },
    "state": "",             # Bundesland für Beschwerden
    "countries": ["de"],     # Länder, in denen die Person gewohnt/gearbeitet hat
    "groups": {"consumer": True, "b2b": True, "adtech": True, "people": True, "credit": False, "us": True},
    "mailbox": {
        "provider": "",
        "address": "",
        "display_name": "",
        "username": "",
        "imap_host": "",
        "imap_port": 993,
        "smtp_host": "",
        "smtp_port": 587,
        "smtp_security": "starttls",   # starttls | ssl
        "save_sent": True,
        "sent_folder": "",
        "verified": False,
    },
    "sending": {
        "per_day": 10,
        "send_time": "09:00",
        "reminder_days": 30,
        "complaint_days": 14,
        "poll_minutes": 15,
        "auto_remind": True,
        "notifications": True,
        "first_batch_now": True,
    },
    "ai": {
        "provider": "none",          # none | apple | ollama | cloud
        "ollama_model": "",
        "ollama_url": "http://127.0.0.1:11434",
        "cloud_vendor": "anthropic", # anthropic | openai
        "cloud_model": "",
    },
    "setup_step": 1,
    "setup_done": False,
    "started": False,
    "imap_state": {"uidvalidity": None, "last_uid": 0},
    "last_poll": None,
    "last_poll_error": None,
    "last_send_error": None,
    "last_broker_update": None,
    "broker_update_info": None,
    "next_ref": 1,
}


def now() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(str(config.db_path()), timeout=30, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    return con


MIGRATIONS = [
    ("messages", "reply_to", "TEXT"),
    ("messages", "received", "TEXT"),
    ("messages", "folder", "TEXT"),
    ("messages", "link", "TEXT"),
]


def init() -> None:
    with _LOCK:
        con = connect()
        try:
            con.executescript(SCHEMA)
            for table, column, kind in MIGRATIONS:
                cols = {r[1] for r in con.execute("PRAGMA table_info(%s)" % table).fetchall()}
                if column not in cols:
                    con.execute("ALTER TABLE %s ADD COLUMN %s %s" % (table, column, kind))
            con.commit()
        finally:
            con.close()


def query(sql: str, params: tuple | list = ()) -> list[dict]:
    with _LOCK:
        con = connect()
        try:
            return [dict(r) for r in con.execute(sql, params).fetchall()]
        finally:
            con.close()


def query_one(sql: str, params: tuple | list = ()) -> dict | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: tuple | list = ()) -> int:
    with _LOCK:
        con = connect()
        try:
            cur = con.execute(sql, params)
            con.commit()
            return cur.lastrowid
        finally:
            con.close()


def get(key: str) -> Any:
    row = query_one("SELECT value FROM settings WHERE key = ?", (key,))
    default = copy.deepcopy(DEFAULTS.get(key))
    if row is None:
        return default
    value = json.loads(row["value"])
    if isinstance(default, dict) and isinstance(value, dict):
        merged = default
        merged.update(value)
        return merged
    return value


def put(key: str, value: Any) -> None:
    execute(
        "INSERT INTO settings(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, json.dumps(value, ensure_ascii=False)),
    )


def update(key: str, **changes: Any) -> dict:
    current = get(key) or {}
    current.update(changes)
    put(key, current)
    return current


def event(request_id: int | None, kind: str, text: str, at: str | None = None) -> None:
    execute(
        "INSERT INTO events(request_id, at, kind, text) VALUES (?, ?, ?, ?)",
        (request_id, at or now(), kind, text),
    )


def next_ref() -> str:
    with _LOCK:
        n = int(get("next_ref") or 1)
        put("next_ref", n + 1)
    return "DA-%03d" % n
