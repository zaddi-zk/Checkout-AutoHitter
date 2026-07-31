# database.py
"""
Database module – all SQLite operations.
"""

import sqlite3
import secrets
import string
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

from config import DB_PATH, ADMINS


def init_db():
    """Create tables if they don't exist."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            telegram_id INTEGER UNIQUE,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key_code TEXT UNIQUE,
            user_id INTEGER,
            days_valid INTEGER,
            expires_at TIMESTAMP,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'pending'
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS mass_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key_code TEXT UNIQUE,
            hours_valid INTEGER,
            expires_at TIMESTAMP,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount_usd REAL,
            crypto_currency TEXT,
            crypto_amount REAL,
            wallet_address TEXT,
            tx_hash TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            key_id INTEGER
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            url TEXT,
            shipping_data TEXT,
            cards TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS checkout_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            url TEXT,
            card_bin TEXT,
            card_last4 TEXT,
            status TEXT,
            message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()


def log_checkout_attempt(user_id: int, url: str, card_bin: str, card_last4: str, status: str, message: str = ""):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO checkout_log (user_id, url, card_bin, card_last4, status, message) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, url, card_bin, card_last4, status, message)
    )
    conn.commit()
    conn.close()


def get_user(telegram_id: int) -> Optional[Dict[str, Any]]:
    """Fetch a user by Telegram ID."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def create_user(telegram_id: int, username: str = "", first_name: str = "", last_name: str = ""):
    """Insert a new user."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT OR IGNORE INTO users (telegram_id, username, first_name, last_name) VALUES (?, ?, ?, ?)",
        (telegram_id, username, first_name, last_name)
    )
    conn.commit()
    conn.close()


def is_admin(telegram_id: int) -> bool:
    """Check if user is in the admin list."""
    return telegram_id in ADMINS


def generate_key(user_id: int, days: int, created_by: int) -> str:
    """Generate a unique 16‑character premium key."""
    key_code = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(16))
    expires_at = datetime.now() + timedelta(days=days)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO keys (key_code, user_id, days_valid, expires_at, created_by, status) VALUES (?, ?, ?, ?, ?, ?)",
        (key_code, user_id, days, expires_at.isoformat(), created_by, 'pending')
    )
    conn.commit()
    conn.close()
    return key_code


def redeem_key(key_code: str, user_id: int) -> Tuple[bool, str]:
    """Redeem a key for a user. Returns (success, message)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("SELECT * FROM keys WHERE key_code = ? AND status = 'pending'", (key_code.upper(),))
    key = c.fetchone()

    if not key:
        conn.close()
        return False, "❌ Invalid or already used key."

    # Activate the key
    c.execute(
        "UPDATE keys SET user_id = ?, status = 'active' WHERE key_code = ?",
        (user_id, key_code.upper())
    )
    conn.commit()
    conn.close()
    return True, f"✅ Key activated! Expires: {key['expires_at']}"


def get_active_key(user_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve the user's currently active key (if any)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(
        "SELECT * FROM keys WHERE user_id = ? AND status = 'active' AND datetime(expires_at) > datetime('now')",
        (user_id,)
    )
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None