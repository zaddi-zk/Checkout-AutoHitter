#!/usr/bin/env python3
"""
🔥 HOTTBOII CHECKOUT BOT v3.0 – PREMIUM EDITION
Fully automated Shopify/Stripe checkout bot with:
- Premium key system (admin generated)
- Crypto payments (BTC, ETH, LTC, USDT)
- Auto-approve workflow with expiry tracking
- Clean, professional UI with emojis
- Live status updates
"""

import logging
import os
import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple
from pathlib import Path

from telegram import CallbackQuery, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    PicklePersistence,
)

# ======================================================================
# CONFIGURATION (Load from .env or hardcode)
# ======================================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 8711230373
DEVELOPER_ID = 8366864444
OWNER_ID = ADMIN_ID  # Same as admin
ADMIN_IDS = [ADMIN_ID, DEVELOPER_ID]

# Wallet addresses
WALLETS: Dict[str, str] = {
    "BTC": "bc1q5vyek2r3hzlarvgf4ycqmqf42tv398ns89u7ep",
    "ETH": "0x0844B1074FA252E8f71971203D175bDC5dbb6251",
    "LTC": "ltc1qahueh8eyg79cqqkn253v2lhnef2ntvkwj4npuz",
    "USDT": "0x0844B1074FA252E8f71971203D175bDC5dbb6251",
}

# Pricing
PRICING: Dict[str, Dict[str, Any]] = {
    "1day": {"days": 1, "price_usd": 15, "crypto": {"BTC": 0.00035, "ETH": 0.006, "LTC": 0.2, "USDT": 15}},
    "3days": {"days": 3, "price_usd": 30, "crypto": {"BTC": 0.0007, "ETH": 0.012, "LTC": 0.4, "USDT": 30}},
    "7days": {"days": 7, "price_usd": 50, "crypto": {"BTC": 0.0012, "ETH": 0.02, "LTC": 0.7, "USDT": 50}},
}

# ======================================================================
# DATABASE (SQLite)
# ======================================================================

import sqlite3
from pathlib import Path
from config import DB_PATH, PremiumIcons

# Checkout handlers (import directly to avoid circular-import type inference issues)
from handlers.checkout import (
    checkout_start,
    handle_checkout_url,
    handle_shipping_line,
    handle_cards,
)

def init_db():
    """Initialize database tables."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Users table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            telegram_id INTEGER UNIQUE,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_admin INTEGER DEFAULT 0,
            is_developer INTEGER DEFAULT 0
        )
    ''')
    
    # Keys table
    c.execute('''
        CREATE TABLE IF NOT EXISTS keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key_code TEXT UNIQUE,
            user_id INTEGER,
            days_valid INTEGER,
            expires_at TIMESTAMP,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'pending'  -- pending, active, expired, revoked
        )
    ''')
    
    # Mass-shared keys table
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
    
    # Payments table
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
    
    # Checkout sessions (for tracking user flow)
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
    logging.info("Database initialized")

def get_user(telegram_id: int) -> Optional[Dict[str, object]]:
    """Get user from database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def create_user(telegram_id: int, username: Optional[str] = "", first_name: Optional[str] = "", last_name: Optional[str] = ""):
    """Create a new user."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT OR IGNORE INTO users (telegram_id, username, first_name, last_name) VALUES (?, ?, ?, ?)",
        (telegram_id, username or "", first_name or "", last_name or "")
    )
    conn.commit()
    conn.close()

def is_admin(telegram_id: int) -> bool:
    """Check if user is admin or developer."""
    return telegram_id in [ADMIN_ID, DEVELOPER_ID, OWNER_ID]

def generate_key(user_id: int, days: int, created_by: int) -> str:
    """Generate a unique premium key."""
    import secrets
    import string
    
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
    """Redeem a premium key for a user."""
    normalized_code = key_code.strip().upper()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute(
        "SELECT * FROM keys WHERE key_code = ? AND status = 'pending'",
        (normalized_code,)
    )
    key = c.fetchone()

    if key:
        c.execute(
            "UPDATE keys SET user_id = ?, status = 'active' WHERE key_code = ?",
            (user_id, normalized_code)
        )
        conn.commit()
        expires_at = key['expires_at']
        conn.close()
        return True, f"✅ Key activated! Expires: {expires_at}"

    c.execute(
        "SELECT * FROM mass_keys WHERE key_code = ? AND datetime(expires_at) > datetime('now')",
        (normalized_code,)
    )
    mass_key = c.fetchone()

    conn.close()

    if mass_key:
        return True, (
            "✅ Shared access key accepted! "
            f"Valid until {mass_key['expires_at']}.")

    return False, "❌ Invalid or already used key."


def get_active_key(user_id: int) -> Optional[Dict[str, object]]:
    """Get user's active premium key or a valid shared mass key."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(
        "SELECT * FROM keys WHERE user_id = ? AND status = 'active' "
        "AND datetime(expires_at) > datetime('now')",
        (user_id,)
    )
    row = c.fetchone()

    if row:
        conn.close()
        return dict(row)

    c.execute(
        "SELECT * FROM mass_keys "
        "WHERE datetime(expires_at) > datetime('now') "
        "ORDER BY expires_at DESC LIMIT 1"
    )
    mass_row = c.fetchone()
    conn.close()

    return dict(mass_row) if mass_row else None


def generate_mass_key(hours: int, created_by: int) -> Dict[str, Any]:
    """Generate a shared mass key valid for many users."""
    import secrets
    import string

    key_code = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(12))
    expires_at = datetime.now() + timedelta(hours=hours)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO mass_keys (key_code, hours_valid, expires_at, created_by) VALUES (?, ?, ?, ?)",
        (key_code, hours, expires_at.isoformat(timespec='seconds'), created_by)
    )
    conn.commit()
    conn.close()

    return {
        'key_code': key_code,
        'hours': hours,
        'expires_at': expires_at.isoformat(timespec='seconds'),
    }

# ======================================================================
# LOGGING
# ======================================================================

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ======================================================================
# CONVERSATION STATES
# ======================================================================

# ======================================================================
# BOT APPLICATION
# ======================================================================

application = None

# ======================================================================
# MENU ASSET RENDERING HELPERS
# ======================================================================

def build_menu_keyboard(user_id: int) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("💳 Checkout", callback_data="checkout")],
        [InlineKeyboardButton("🔑 Get Access Key", callback_data="get_key")],
        [InlineKeyboardButton("👤 Profile", callback_data="profile")],
        [InlineKeyboardButton("💎 About", callback_data="about")],
        [InlineKeyboardButton("🛠 Support", callback_data="support")],
    ]
    if is_admin(user_id):
        keyboard.append([InlineKeyboardButton("🔐 Admin Panel", callback_data="admin_panel")])
    return InlineKeyboardMarkup(keyboard)


def build_back_keyboard(callback_data: str = "back_to_start") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("◀️ Back", callback_data=callback_data)]
    ])


def build_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Cancel", callback_data="back_to_start")]
    ])


async def forward_payment_proof_to_admins(payment_db_id: int, payment_info: Dict[str, Any], context: ContextTypes.DEFAULT_TYPE, proof_text: Optional[str] = None, photo_file_id: Optional[str] = None, document_file_id: Optional[str] = None) -> None:
    caption = (
        f"{PremiumIcons.CREDIT_CARD} <b>Payment Proof Received</b>\n\n"
        f"👤 User: <code>{payment_info['user_id']}</code>\n"
        f"📦 Plan: {payment_info['plan']}\n"
        f"💰 Amount: ${payment_info['amount']}\n"
        f"💎 Crypto: {payment_info['crypto']}\n"
        f"📌 Wallet: <code>{payment_info['wallet']}</code>\n"
        f"🆔 Payment ID: <code>{payment_info['payment_id']}</code>\n"
        f"\n{proof_text or 'Proof attached below.'}\n\n"
        f"Use the buttons below to approve fast:\n"
        f"/approve_{payment_db_id}_1 for 1 day\n"
        f"/approve_{payment_db_id}_3 for 3 days\n"
        f"/approve_{payment_db_id}_7 for 7 days\n"
    )

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Approve 1D", callback_data=f"approve_{payment_db_id}_1"), InlineKeyboardButton("✅ Approve 3D", callback_data=f"approve_{payment_db_id}_3"), InlineKeyboardButton("✅ Approve 7D", callback_data=f"approve_{payment_db_id}_7")],
        [InlineKeyboardButton("❌ Decline", callback_data=f"decline_{payment_db_id}")]
    ])

    for admin_id in set(ADMIN_IDS):
        try:
            if photo_file_id:
                await context.bot.send_photo(admin_id, photo_file_id, caption=caption, reply_markup=buttons, parse_mode="HTML")
            elif document_file_id:
                await context.bot.send_document(admin_id, document_file_id, caption=caption, reply_markup=buttons, parse_mode="HTML")
            else:
                await context.bot.send_message(admin_id, caption, reply_markup=buttons, parse_mode="HTML")
        except Exception as exc:
            logger.error("Failed to forward payment proof to admin %s: %s", admin_id, exc)


def luxury_card_asset(state: str, action_note: str = "") -> str:
    label = "<b>💎 PREMIUM CHECKOUT SUITE</b>"
    if state == "action" and action_note:
        return f"💳 {label} <i>• {action_note}</i>"
    return f"💳 {label}"


def vault_ledger_asset(state: str, action_note: str = "") -> str:
    label = "<b>⚡ REAL‑TIME AUTO‑HITTER</b>"
    if state == "action" and action_note:
        return f"🔒 {label} <i>• {action_note}</i>"
    return f"🔒 {label}"


def render_main_menu(user_id: int, asset_type: str = "card", asset_state: str = "idle", action_note: str = "") -> str:
    card_block = luxury_card_asset(asset_state if asset_type == "card" else "idle", action_note if asset_type == "card" else "")
    vault_block = vault_ledger_asset(asset_state if asset_type == "vault" else "idle", action_note if asset_type == "vault" else "")

    return (
        "🔥 <b>HOTTBOII CHECKOUT BOT v3.0</b> 🔥\n\n"
        f"{card_block}\n"
        f"{vault_block}\n\n"
        "<i>Tap a button below to continue.</i>"
    )


async def render_menu_transition(query: CallbackQuery, asset_type: str, action_note: str) -> Any:
    """Show the menu in a temporary action state before the final screen."""
    assert query.from_user is not None
    assert query.message is not None
    return await query.edit_message_text(
        render_main_menu(query.from_user.id, asset_type=asset_type, asset_state="action", action_note=action_note),
        reply_markup=query.message.reply_markup,
        parse_mode="HTML"
    )


async def safe_answer_callback_query(query: Optional[CallbackQuery], text: Optional[str] = None, show_alert: bool = False) -> None:
    if query is None:
        return
    try:
        await query.answer(text=text, show_alert=show_alert)
    except BadRequest as exc:
        error_text = str(exc)
        if "Query is too old" in error_text or "response timeout expired" in error_text or "query id is invalid" in error_text:
            logger.warning("Ignored expired callback query answer: %s", exc)
            return
        raise


# ======================================================================
# START COMMAND
# ======================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send the main menu."""
    user = update.effective_user
    if user is None or update.message is None:
        return

    assert update.message is not None
    create_user(user.id, user.username, user.first_name, user.last_name)

    await update.message.reply_text(
        render_main_menu(user.id),
        reply_markup=build_menu_keyboard(user.id),
        parse_mode="HTML"
    )

async def profile_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the user profile dashboard."""
    query = update.callback_query
    if query is None or update.effective_user is None:
        return
    assert query.message is not None
    await safe_answer_callback_query(query)

    user = update.effective_user

    active_key = get_active_key(user.id)
    key_status = (
        f"<b>Active</b> • Expires <code>{active_key.get('expires_at')}</code>"
        if active_key
        else "<b>Inactive</b> • No active key"
    )

    username_display = f"@{user.username}" if user.username else "<i>username not set</i>"
    user_name = user.full_name or username_display

    await query.edit_message_text(
        f"{PremiumIcons.BRIEFCASE} <b>Premium Dashboard</b> {PremiumIcons.BRIEFCASE}\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>User:</b> {user_name}\n"
        f"<b>Telegram ID:</b> <code>{user.id}</code>\n"
        f"<b>Username:</b> {username_display}\n"
        f"<b>Key status:</b> {PremiumIcons.VERIFIED} {key_status}\n\n"
        f"{PremiumIcons.MONEY_BAG} <b>What you can do:</b>\n"
        "• Start a checkout\n"
        "• Purchase or renew a key\n"
        "• Contact support instantly\n\n"
        "<b>Tip:</b> Keep your premium key active for uninterrupted checkout flow.",
        reply_markup=build_menu_keyboard(user.id),
        parse_mode="HTML"
    )

# ======================================================================
# ABOUT COMMAND
# ======================================================================

async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show about information."""
    query = update.callback_query
    if query is None or update.effective_user is None:
        return
    assert query.message is not None
    await safe_answer_callback_query(query)

    await query.edit_message_text(
        f"{PremiumIcons.BRIEFCASE} <b>About HOTTBOII Checkout Bot</b> {PremiumIcons.BRIEFCASE}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "This bot automates checkout processes for:\n"
        "• Shopify stores\n"
        "• Stripe checkout pages\n"
        "• WooCommerce\n\n"
        f"{PremiumIcons.SECRET_KEY} <b>How it works:</b>\n"
        "1. Get an access key (crypto payment)\n"
        "2. Provide checkout URL\n"
        "3. Provide shipping details\n"
        "4. Provide CCs (one per line)\n"
        "5. Bot auto-fills and attempts checkout\n\n"
        f"{PremiumIcons.INBOX} <b>Contact:</b> @hottboiihitzz\n\n"
        f"{PremiumIcons.FIRE} <b>Trusted by 1,000+ users</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ Back", callback_data="back_to_start")]
        ])
    )

# ======================================================================
# SUPPORT COMMAND
# ======================================================================

async def support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Redirect to support."""
    query = update.callback_query
    if query is None or update.effective_user is None:
        return
    assert query.message is not None
    await safe_answer_callback_query(query)

    await query.edit_message_text(
        f"{PremiumIcons.ALERT} <b>Support Center</b> {PremiumIcons.ALERT}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{PremiumIcons.INBOX} <b>DM me directly:</b> @hottboiihitzz\n\n"
        f"{PremiumIcons.FIRE} <b>Response time:</b> <i>under 5 minutes</i>\n\n"
        "<b>Please include your order details if reporting an issue.</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📧 Contact Support", url="https://t.me/hottboiihitzz")],
            [InlineKeyboardButton("◀️ Back", callback_data="back_to_start")]
        ])
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help information."""
    if update.message is None:
        return
    assert update.message is not None
    await update.message.reply_text(
        f"{PremiumIcons.ALERT} <b>Help & Commands</b>\n\n"
        "<code>/start</code> - Open the main menu\n"
        "<code>/redeem &lt;key&gt;</code> - Activate your premium key\n"
        "<code>/help</code> - Show this help message\n"
        "<code>/settings</code> - View your account status\n"
        "<code>/about</code> - Learn more about the bot\n\n"
        "Use the menu buttons for fast navigation.",
        parse_mode="HTML"
    )


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show current account status."""
    user = update.effective_user
    if user is None or update.message is None:
        return
    assert update.message is not None

    active_key = get_active_key(user.id)

    if active_key:
        expires_at = active_key.get('expires_at')
        await update.message.reply_text(
            f"🔒 <b>Account Status</b>\n\n"
            f"Premium key is active.\n"
            f"Expires: {expires_at}\n"
            f"Use /redeem to activate additional keys or /getkey to purchase more.",
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text(
            f"🔓 <b>Account Status</b>\n\n"
            "No active premium key found.\n"
            "Use /getkey or the menu to purchase access.",
            parse_mode="HTML"
        )

# ======================================================================
# GET KEY / PAYMENT FLOW
# ======================================================================

async def get_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start payment flow for access key."""
    query = update.callback_query
    if query is None:
        return
    await safe_answer_callback_query(query)

    keyboard = [
        [InlineKeyboardButton("1 Day – $15", callback_data="pay_1day")],
        [InlineKeyboardButton("3 Days – $30", callback_data="pay_3days")],
        [InlineKeyboardButton("7 Days – $50", callback_data="pay_7days")],
        [InlineKeyboardButton("◀️ Back", callback_data="back_to_start")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"{PremiumIcons.MONEY_BAG} <b>Get Access Key</b>\n\n"
        "Choose your plan:\n\n"
        "🟢 <b>1 Day</b> – $15 (0.00035 BTC / 0.006 ETH / 0.2 LTC / 15 USDT)\n"
        "🟡 <b>3 Days</b> – $30 (0.0007 BTC / 0.012 ETH / 0.4 LTC / 30 USDT)\n"
        "🔴 <b>7 Days</b> – $50 (0.0012 BTC / 0.02 ETH / 0.7 LTC / 50 USDT)\n\n"
        "💳 <b>Payment methods:</b> BTC, ETH, LTC, USDT (ERC-20)\n\n"
        "Select a plan to proceed:",
        reply_markup=reply_markup,
        parse_mode="HTML"
    )

async def payment_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle payment plan selection."""
    query = update.callback_query
    if query is None or query.data is None or context.user_data is None:
        return
    assert query.message is not None
    await safe_answer_callback_query(query)

    plan_key = query.data.replace("pay_", "")
    plan = PRICING.get(plan_key)
    
    if not plan:
        await query.edit_message_text(
            "❌ Invalid plan selected.",
            reply_markup=build_back_keyboard("get_key")
        )
        return
    
    # Store selected plan in context
    context.user_data['selected_plan'] = plan_key
    
    keyboard = [
        [InlineKeyboardButton("₿ Bitcoin (BTC)", callback_data=f"pay_method_BTC_{plan_key}")],
        [InlineKeyboardButton("⟠ Ethereum (ETH)", callback_data=f"pay_method_ETH_{plan_key}")],
        [InlineKeyboardButton("Ł Litecoin (LTC)", callback_data=f"pay_method_LTC_{plan_key}")],
        [InlineKeyboardButton("💵 USDT (ERC-20)", callback_data=f"pay_method_USDT_{plan_key}")],
        [InlineKeyboardButton("◀️ Back", callback_data="get_key")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"{PremiumIcons.CREDIT_CARD} <b>Payment Method Selection</b>\n\n"
        f"Plan: <b>{plan['days']} days</b> – ${plan['price_usd']}\n\n"
        f"Select your preferred cryptocurrency:",
        reply_markup=reply_markup,
        parse_mode="HTML"
    )

async def payment_method_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show payment instructions."""
    query = update.callback_query
    if query is None or query.data is None or context.user_data is None:
        return
    assert query.message is not None
    await safe_answer_callback_query(query)
    
    parts = query.data.split("_")
    if len(parts) != 4:
        await query.edit_message_text(
            "❌ Invalid selection.",
            reply_markup=build_back_keyboard("get_key")
        )
        return

    crypto = parts[2]
    plan_key = parts[3]
    plan = PRICING.get(plan_key)
    
    if not plan:
        await query.edit_message_text(
            "❌ Invalid selection.",
            reply_markup=build_back_keyboard("get_key")
        )
        return
    
    wallet_address = WALLETS.get(crypto)
    crypto_amount = plan["crypto"].get(crypto)
    usd_amount = plan["price_usd"]
    days = plan["days"]
    
    payment_id = f"PAY_{datetime.now().strftime('%Y%m%d%H%M%S')}_{query.from_user.id}"
    
    keyboard = [
        [InlineKeyboardButton("✅ Verify Payment", callback_data=f"payment_done_{payment_id}")],
        [InlineKeyboardButton("◀️ Back", callback_data="get_key")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"{PremiumIcons.CREDIT_CARD} <b>Payment Instructions</b>\n\n"
        f"🆔 <b>Payment ID:</b> <code>{payment_id}</code>\n"
        f"📦 <b>Plan:</b> {days} days – ${usd_amount}\n"
        f"💎 <b>Crypto:</b> {crypto}\n"
        f"📊 <b>Amount:</b> {crypto_amount} {crypto}\n\n"
        f"<b>Send payment to this address:</b>\n"
        f"<code>{wallet_address}</code>\n\n"
        f"<b>Other supported wallets:</b>\n"
        f"BTC – <code>{WALLETS['BTC']}</code>\n"
        f"ETH – <code>{WALLETS['ETH']}</code>\n"
        f"LTC – <code>{WALLETS['LTC']}</code>\n"
        f"USDT ERC-20 – <code>{WALLETS['USDT']}</code>\n\n"
        f"⚠️ <i>Send the EXACT amount shown above.</i>\n"
        f"⏱ <i>Payment expires in 1 hour.</i>\n\n"
        f"After sending, click \"Verify Payment\" and send your proof screenshot or TXID here.",
        reply_markup=reply_markup,
        parse_mode="HTML"
    )
    
    # Store payment info for approval
    context.user_data['pending_payment'] = {
        'payment_id': payment_id,
        'plan': plan_key,
        'crypto': crypto,
        'amount': crypto_amount,
        'wallet': wallet_address,
        'user_id': query.from_user.id
    }

async def payment_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle payment verification request."""
    query = update.callback_query
    if query is None or query.data is None or context.user_data is None:
        return
    assert query.message is not None
    await safe_answer_callback_query(query)
    
    payment_id = query.data.replace("payment_done_", "")
    
    await query.edit_message_text(
        f"{PremiumIcons.ALERT} <b>Payment Verification</b>\n\n"
        "Please send your payment proof screenshot or TXID now.\n\n"
        "Example: <code>0x...</code> or <code>bc1...</code>\n\n"
        "Your proof will be forwarded to the team for approval.",
        parse_mode="HTML",
        reply_markup=build_back_keyboard()
    )
    
    context.user_data['awaiting_tx'] = True
    context.user_data['payment_id'] = payment_id

async def handle_payment_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle payment proof submission from the user."""
    if update.message is None or update.effective_user is None or context.user_data is None:
        return

    if not context.user_data.get('awaiting_tx'):
        return

    payment_info = context.user_data.get('pending_payment', {})
    if not payment_info:
        await update.message.reply_text("❌ No pending payment found. Please restart the payment process.")
        context.user_data['awaiting_tx'] = False
        return

    proof_text = None
    photo_file_id = None
    document_file_id = None

    if update.message.photo:
        photo_file_id = update.message.photo[-1].file_id
        proof_text = update.message.caption or "Payment proof screenshot attached."
    elif update.message.document:
        document_file_id = update.message.document.file_id
        proof_text = update.message.caption or "Payment proof document attached."
    elif update.message.text:
        proof_text = update.message.text.strip()
        if len(proof_text) < 10:
            await update.message.reply_text("❌ Invalid TXID or proof text. Please send a valid TXID or screenshot.")
            return
    else:
        await update.message.reply_text("❌ Please send a screenshot, document, or TXID for payment proof.")
        return

    plan_key = payment_info.get('plan')
    plan = PRICING.get(plan_key) or {}

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO payments (user_id, amount_usd, crypto_currency, crypto_amount, wallet_address, tx_hash, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            update.effective_user.id,
            plan.get('price_usd', 0),
            payment_info.get('crypto', 'BTC'),
            payment_info.get('amount', 0),
            payment_info.get('wallet', ''),
            proof_text,
            'pending'
        )
    )
    payment_db_id = int(c.lastrowid or 0)
    conn.commit()
    conn.close()

    await forward_payment_proof_to_admins(
        payment_db_id,
        {
            'user_id': update.effective_user.id,
            'plan': plan_key,
            'amount': payment_info.get('amount', 0),
            'crypto': payment_info.get('crypto', 'BTC'),
            'wallet': payment_info.get('wallet', ''),
            'payment_id': payment_info.get('payment_id', '')
        },
        context,
        proof_text=proof_text,
        photo_file_id=photo_file_id,
        document_file_id=document_file_id
    )

    await update.message.reply_text(
        f"{PremiumIcons.VERIFIED} <b>Payment Proof Submitted</b>\n\n"
        "Your payment proof has been received. Hang on for the team approval.\n\n"
        "You will be notified once your premium key is ready.",
        parse_mode="HTML"
    )

    context.user_data['awaiting_tx'] = False
    context.user_data['pending_payment'] = None

# ======================================================================
# ADMIN PANEL
# ======================================================================

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin panel."""
    user = update.effective_user
    query = update.callback_query
    if query is None or user is None:
        return
    if not is_admin(user.id):
        await safe_answer_callback_query(query, "⛔ Access denied.", show_alert=True)
        return
    await safe_answer_callback_query(query)
    
    keyboard = [
        [InlineKeyboardButton("🔑 Generate Keys", callback_data="admin_gen_keys")],
        [InlineKeyboardButton("🧩 Generate Mass Key", callback_data="admin_mass_key")],
        [InlineKeyboardButton("📊 View Users", callback_data="admin_users")],
        [InlineKeyboardButton("📈 View Payments", callback_data="admin_payments")],
        [InlineKeyboardButton("📋 Pending Keys", callback_data="admin_pending")],
        [InlineKeyboardButton("◀️ Back", callback_data="back_to_start")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"{PremiumIcons.VERIFIED} <b>Admin Panel</b> {PremiumIcons.VERIFIED}\n\n"
        "Welcome, Admin.\n\n"
        "Select an action:\n\n"
        "• Generate one-off keys\n"
        "• Generate a shared mass key for all users\n"
        "• Review users, payments, and pending items",
        reply_markup=reply_markup,
        parse_mode="HTML"
    )

async def admin_gen_keys(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate keys for a user."""
    query = update.callback_query
    if not query:
        return
    await safe_answer_callback_query(query)
    
    await query.edit_message_text(
        f"{PremiumIcons.SECRET_KEY} <b>Generate Premium Keys</b> {PremiumIcons.SECRET_KEY}\n\n"
        "Send the details in this format:\n\n"
        "<code>/genkey &lt;user_id&gt; &lt;days&gt;</code>\n\n"
        "Example:\n"
        "<code>/genkey 8711230373 7</code>\n\n"
        "This will generate a 7-day key for user 8711230373.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ Back", callback_data="admin_panel")]
        ])
    )

async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user list to admin."""
    query = update.callback_query
    if query is None or update.effective_user is None:
        return
    if not is_admin(update.effective_user.id):
        await safe_answer_callback_query(query, "⛔ Access denied.", show_alert=True)
        return
    await safe_answer_callback_query(query)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT telegram_id, username, first_name, last_name, created_at FROM users ORDER BY created_at DESC LIMIT 20")
    rows = c.fetchall()
    conn.close()

    text = f"{PremiumIcons.SECRET_KEY} <b>Recent Users</b>\n\n"
    if not rows:
        text += "No users found yet."
    else:
        for row in rows:
            username = row['username'] or 'no username'
            full_name = f"{row['first_name'] or ''} {row['last_name'] or ''}".strip()
            text += f"👤 <code>{row['telegram_id']}</code> | {username} | {full_name}\n"
        text += "\nShowing up to 20 records."

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ Back", callback_data="admin_panel")]
        ])
    )

async def admin_payments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show payment records to admin."""
    query = update.callback_query
    if query is None or update.effective_user is None:
        return
    if not is_admin(update.effective_user.id):
        await safe_answer_callback_query(query, "⛔ Access denied.", show_alert=True)
        return
    await safe_answer_callback_query(query)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT id, user_id, crypto_currency, crypto_amount, amount_usd, status, created_at FROM payments ORDER BY created_at DESC LIMIT 20")
    rows = c.fetchall()
    conn.close()

    text = f"{PremiumIcons.CREDIT_CARD} <b>Recent Payments</b>\n\n"
    if not rows:
        text += "No payment records found."
    else:
        for row in rows:
            text += f"#{row['id']} <code>{row['user_id']}</code> | {row['crypto_currency']} {row['crypto_amount']} | ${row['amount_usd']} | {row['status']}\n"
        text += "\nShowing up to 20 records."

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ Back", callback_data="admin_panel")]
        ])
    )

async def admin_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show pending keys to admin."""
    query = update.callback_query
    if query is None or update.effective_user is None:
        return
    if not is_admin(update.effective_user.id):
        await safe_answer_callback_query(query, "⛔ Access denied.", show_alert=True)
        return
    await safe_answer_callback_query(query)

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT key_code, user_id, days_valid, expires_at, created_at FROM keys WHERE status = 'pending' ORDER BY created_at DESC LIMIT 20")
        rows = c.fetchall()
        conn.close()
    except Exception:
        logger.exception("Failed to load pending keys")
        await query.edit_message_text(
            "❌ Failed to load pending keys. Please try again later.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀️ Back", callback_data="admin_panel")]
            ])
        )
        return

    text = f"{PremiumIcons.SECRET_KEY} <b>Pending Keys</b>\n\n"
    if not rows:
        text += "No pending keys found."
    else:
        for row in rows:
            text += f"<code>{row['key_code']}</code> | <code>{row['user_id']}</code> | {row['days_valid']}d | expires {row['expires_at']}\n"
        text += "\nShowing up to 20 records."

    if len(text) > 3900:
        text = f"{PremiumIcons.SECRET_KEY} <b>Pending Keys</b>\n\n"
        text += f"There are {len(rows)} pending keys, but the list is too large to display here.\n"
        text += "Use the database or a dedicated admin tool to inspect them."

    try:
        await query.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀️ Back", callback_data="admin_panel")]
            ])
        )
    except BadRequest:
        if query.message is not None:
            await query.message.reply_text(
                text,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("◀️ Back", callback_data="admin_panel")]
                ])
            )

async def admin_mass_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show shared mass key creation options."""
    query = update.callback_query
    if query is None or update.effective_user is None:
        return
    if query.data is None:
        return
    if not is_admin(update.effective_user.id):
        await safe_answer_callback_query(query, "⛔ Access denied.", show_alert=True)
        return
    await safe_answer_callback_query(query)

    await query.edit_message_text(
        f"{PremiumIcons.SECRET_KEY} <b>Generate Shared Mass Key</b> {PremiumIcons.SECRET_KEY}\n\n"
        "Choose the shared duration for the mass key:\n\n"
        "• 3 hours\n"
        "• 6 hours\n\n"
        "This key is valid for all users and can be posted in your channel.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("3 Hours", callback_data="masskey_3")],
            [InlineKeyboardButton("6 Hours", callback_data="masskey_6")],
            [InlineKeyboardButton("◀️ Back", callback_data="admin_panel")],
        ])
    )

async def admin_mass_key_create(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Create a shared mass key and notify existing users."""
    query = update.callback_query
    if query is None or update.effective_user is None:
        return
    if query.data is None:
        return
    if not is_admin(update.effective_user.id):
        await safe_answer_callback_query(query, "⛔ Access denied.", show_alert=True)
        return
    await safe_answer_callback_query(query)

    hours = 3 if query.data.endswith("_3") else 6
    mass_key = generate_mass_key(hours, update.effective_user.id)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT telegram_id FROM users")
    users = [row['telegram_id'] for row in c.fetchall()]
    conn.close()

    sent = 0
    for telegram_id in users:
        try:
            await context.bot.send_message(
                telegram_id,
                f"{PremiumIcons.FIRE} <b>Shared Access Key Generated</b>\n\n"
                f"A shared premium key has been generated for {hours} hours.\n"
                f"<code>{mass_key['key_code']}</code>\n\n"
                f"Use <code>/redeem</code> before {mass_key['expires_at']}.",
                parse_mode="HTML"
            )
            sent += 1
        except Exception:
            continue

    await query.edit_message_text(
        f"{PremiumIcons.SECRET_KEY} <b>Mass Key Created</b>\n\n"
        f"Key: <code>{mass_key['key_code']}</code>\n"
        f"Valid for: {hours} hours\n"
        f"Expires: {mass_key['expires_at']}\n\n"
        f"Share this in your channel like this:\n"
        f"<code>Generate mass key: {mass_key['key_code']}</code>\n\n"
        f"Users notified: {sent}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("◀️ Back to Admin", callback_data="admin_panel")]
        ])
    )

async def handle_genkey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle key generation."""
    user = update.effective_user
    if update.message is None or user is None or not is_admin(user.id):
        return
    
    try:
        args = context.args or []
        if len(args) < 2:
            await update.message.reply_text(
                f"{PremiumIcons.ALERT} <b>Usage:</b> <code>/genkey &lt;user_id&gt; &lt;days&gt;</code>\n\n"
                "Example: <code>/genkey 8711230373 7</code>",
                parse_mode="HTML"
            )
            return
        
        target_user_id = int(args[0])
        days = int(args[1])
        
        if days <= 0:
            await update.message.reply_text("❌ Days must be positive.")
            return
        
        key_code = generate_key(target_user_id, days, user.id)
        
        # Notify admin
        await update.message.reply_text(
            f"{PremiumIcons.VERIFIED} <b>Key Generated</b>\n\n"
            f"👤 User: <code>{target_user_id}</code>\n"
            f"📅 Days: <code>{days}</code>\n"
            f"{PremiumIcons.SECRET_KEY} Key: <code>{key_code}</code>\n\n"
            f"Send this key to the user.",
            parse_mode="HTML"
        )

        # Notify user
        try:
            await context.bot.send_message(
                target_user_id,
                f"{PremiumIcons.FIRE} <b>Premium Key Generated For You</b>\n\n"
                f"{PremiumIcons.SECRET_KEY} <b>Your Key:</b> <code>{key_code}</code>\n"
                f"📅 <b>Validity:</b> {days} days\n\n"
                f"Use <code>/redeem {key_code}</code> to activate.",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Failed to notify user: {e}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

# ======================================================================
# REDEEM KEY
# ======================================================================

async def redeem_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Redeem a premium key."""
    user = update.effective_user
    if update.message is None or user is None:
        return

    try:
        args = context.args or []
        if len(args) < 1:
            await update.message.reply_text(
                f"{PremiumIcons.SECRET_KEY} <b>Redeem Key</b>\n\n"
                "Usage: <code>/redeem &lt;key_code&gt;</code>\n\n"
                "Example: <code>/redeem ABC123XYZ</code>",
                parse_mode="HTML"
            )
            return
        
        key_code = args[0].upper()
        _, message = redeem_key(key_code, user.id)
        await update.message.reply_text(message)
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

# ======================================================================
# CHECKOUT FLOW
# ======================================================================

# Checkout flow handlers moved to handlers/checkout.py – import used above.
# We only keep a lightweight text router here that delegates to the handlers.

async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Route text input based on the current user flow state (delegates to handlers)."""
    if update.message is None:
        return
    if context.user_data is None:
        await update.message.reply_text("⚠️ Session error. Please use /start to restart.")
        return
    user_data = context.user_data

    if user_data.get('awaiting_tx'):
        try:
            await handle_payment_proof(update, context)
        except Exception as e:
            logger.exception("Error in payment_proof handler")
            await update.message.reply_text(f"⚠️ Error processing payment: {e}")
        return

    step = user_data.get('checkout_step')
    try:
        if step == 'waiting_url':
            await handle_checkout_url(update, context)
        elif step == 'waiting_shipping':
            await handle_shipping_line(update, context)
        elif step == 'waiting_cards':
            await handle_cards(update, context)
        else:
            await update.message.reply_text(
                "❗ I didn't understand that. Use /start to open the menu or /help for commands."
            )
    except Exception as e:
        logger.exception("Checkout handler error")
        try:
            await update.message.reply_text(f"⚠️ Error: {e}")
        except Exception:
            pass

# ======================================================================
# ADMIN APPROVAL CALLBACKS
# ======================================================================

async def _finalize_admin_approval(
    payment_db_id: int,
    days: int,
    approver_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    query: Optional[CallbackQuery] = None,
    response_chat_id: Optional[int] = None,
) -> None:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id FROM payments WHERE id = ?", (payment_db_id,))
    row = c.fetchone()

    if not row:
        if query is not None:
            await query.edit_message_text(
                "❌ Payment not found.",
                reply_markup=build_back_keyboard("admin_panel")
            )
        elif response_chat_id is not None:
            await context.bot.send_message(response_chat_id, "❌ Payment not found.")
        conn.close()
        return

    user_id = row[0]
    key_code = generate_key(user_id, days, approver_id)
    c.execute("UPDATE payments SET status = 'approved' WHERE id = ?", (payment_db_id,))
    conn.commit()
    conn.close()

    if query is not None:
        await query.edit_message_text(
            f"{PremiumIcons.VERIFIED} <b>Payment Approved</b>\n\n"
            f"👤 User: <code>{user_id}</code>\n"
            f"📅 Days: <code>{days}</code>\n"
            f"{PremiumIcons.SECRET_KEY} Key: <code>{key_code}</code>\n\n"
            f"User has been notified.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀️ Back to Admin", callback_data="admin_panel")]
            ])
        )
    elif response_chat_id is not None:
        await context.bot.send_message(
            response_chat_id,
            f"{PremiumIcons.VERIFIED} <b>Payment Approved</b>\n\n"
            f"👤 User: <code>{user_id}</code>\n"
            f"📅 Days: <code>{days}</code>\n"
            f"{PremiumIcons.SECRET_KEY} Key: <code>{key_code}</code>\n\n"
            f"User has been notified.",
            parse_mode="HTML"
        )

    try:
        await context.bot.send_message(
            user_id,
            f"{PremiumIcons.FIRE} <b>Payment Approved!</b> 🎉\n\n"
            f"Your premium key is ready:\n"
            f"{PremiumIcons.SECRET_KEY} <code>{key_code}</code>\n\n"
            f"📅 <b>Validity:</b> {days} days\n\n"
            f"Use <code>/redeem {key_code}</code> to activate.",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Failed to notify user: %s", e)


async def _finalize_admin_decline(
    payment_db_id: int,
    context: ContextTypes.DEFAULT_TYPE,
    query: Optional[CallbackQuery] = None,
    response_chat_id: Optional[int] = None,
) -> None:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id FROM payments WHERE id = ?", (payment_db_id,))
    row = c.fetchone()

    if not row:
        if query is not None:
            await query.edit_message_text(
                "❌ Payment not found.",
                reply_markup=build_back_keyboard("admin_panel")
            )
        elif response_chat_id is not None:
            await context.bot.send_message(response_chat_id, "❌ Payment not found.")
        conn.close()
        return

    user_id = row[0]
    c.execute("UPDATE payments SET status = 'declined' WHERE id = ?", (payment_db_id,))
    conn.commit()
    conn.close()

    if query is not None:
        await query.edit_message_text(
            f"{PremiumIcons.ALERT} <b>Payment Declined</b>\n\n"
            f"👤 User: <code>{user_id}</code>\n\n"
            f"User has been notified.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀️ Back to Admin", callback_data="admin_panel")]
            ])
        )
    elif response_chat_id is not None:
        await context.bot.send_message(
            response_chat_id,
            f"{PremiumIcons.ALERT} <b>Payment Declined</b>\n\n"
            f"👤 User: <code>{user_id}</code>\n\n"
            f"User has been notified.",
            parse_mode="HTML"
        )

    try:
        await context.bot.send_message(
            user_id,
            f"{PremiumIcons.ALERT} <b>Payment Declined</b>\n\n"
            f"Your payment was not approved.\n\n"
            f"Please contact support for assistance.",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Failed to notify user: %s", e)


async def admin_approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin approval of payment."""
    query = update.callback_query
    if query is None or update.effective_user is None or query.data is None:
        return
    await safe_answer_callback_query(query)

    if not is_admin(update.effective_user.id):
        await safe_answer_callback_query(query, "⛔ Access denied.", show_alert=True)
        return

    parts = query.data.split("_")
    if len(parts) != 3:
        return
    payment_db_id = int(parts[1])
    days = int(parts[2])

    await _finalize_admin_approval(payment_db_id, days, update.effective_user.id, context, query=query)


async def admin_decline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin declining payment."""
    query = update.callback_query
    if query is None or update.effective_user is None or query.data is None:
        return
    await safe_answer_callback_query(query)

    if not is_admin(update.effective_user.id):
        await safe_answer_callback_query(query, "⛔ Access denied.", show_alert=True)
        return

    parts = query.data.split("_")
    if len(parts) != 2:
        return
    payment_db_id = int(parts[1])

    await _finalize_admin_decline(payment_db_id, context, query=query)

# ======================================================================
# BACK TO START
# ======================================================================

async def approve_text_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle typed approval commands like /approve_123_1."""
    if update.message is None or update.effective_user is None:
        return
    if update.message.text is None:
        return
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Access denied.")
        return

    parts = update.message.text.strip().lstrip('/').split('_')
    if len(parts) != 3 or parts[0] != 'approve':
        await update.message.reply_text("❌ Invalid approve command. Use /approve_<payment_id>_<days>.")
        return

    try:
        payment_db_id = int(parts[1])
        days = int(parts[2])
    except ValueError:
        await update.message.reply_text("❌ Invalid approve command format.")
        return

    await _finalize_admin_approval(
        payment_db_id,
        days,
        update.effective_user.id,
        context,
        response_chat_id=update.effective_user.id,
    )


async def decline_text_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle typed decline commands like /decline_123."""
    if update.message is None or update.effective_user is None:
        return
    if update.message.text is None:
        return
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Access denied.")
        return

    parts = update.message.text.strip().lstrip('/').split('_')
    if len(parts) != 2 or parts[0] != 'decline':
        await update.message.reply_text("❌ Invalid decline command. Use /decline_<payment_id>.")
        return

    try:
        payment_db_id = int(parts[1])
    except ValueError:
        await update.message.reply_text("❌ Invalid decline command format.")
        return

    await _finalize_admin_decline(
        payment_db_id,
        context,
        response_chat_id=update.effective_user.id,
    )

async def back_to_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Return to main menu."""
    query = update.callback_query
    if query is None:
        return
    await safe_answer_callback_query(query)

    await query.edit_message_text(
        render_main_menu(query.from_user.id),
        reply_markup=build_menu_keyboard(query.from_user.id),
        parse_mode="HTML"
    )

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    err = context.error if context.error else "Unknown error"
    logger.error("Update error: %s", err)
    try:
        if not isinstance(update, Update):
            return
        if update.callback_query:
            try:
                await update.callback_query.answer(f"⚠️ {err}", show_alert=True)
            except Exception:
                await update.callback_query.edit_message_text(f"⚠️ Error: {err}")
        elif update.effective_message:
            await update.effective_message.reply_text(f"⚠️ Error: {err}")
    except Exception:
        pass

# ======================================================================
# MAIN
# ======================================================================

def main():
    """Start the bot."""
    global application
    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN is not set. Set the BOT_TOKEN environment variable "
            "(add it as a Railway variable in your service)."
        )
    persistence = PicklePersistence(filepath=str(DB_PATH.parent / "bot_data.pkl"), single_file=False)
    application = Application.builder().token(BOT_TOKEN).persistence(persistence).build()

    # Initialize database
    init_db()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("redeem", redeem_command))
    application.add_handler(CommandHandler("genkey", handle_genkey))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("settings", settings_command))
    
    # Add callback handlers
    application.add_handler(CallbackQueryHandler(about, pattern="^about$"))
    application.add_handler(CallbackQueryHandler(support, pattern="^support$"))
    application.add_handler(CallbackQueryHandler(get_key, pattern="^get_key$"))
    application.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_panel$"))
    application.add_handler(CallbackQueryHandler(admin_gen_keys, pattern="^admin_gen_keys$"))
    application.add_handler(CallbackQueryHandler(admin_mass_key, pattern="^admin_mass_key$"))
    application.add_handler(CallbackQueryHandler(admin_mass_key_create, pattern=r"^masskey_\d+$"))
    application.add_handler(CallbackQueryHandler(admin_users, pattern="^admin_users$"))
    application.add_handler(CallbackQueryHandler(admin_payments, pattern="^admin_payments$"))
    application.add_handler(CallbackQueryHandler(admin_pending, pattern="^admin_pending$"))
    application.add_handler(CallbackQueryHandler(payment_method_selected, pattern="^pay_method_"))
    application.add_handler(CallbackQueryHandler(payment_selected, pattern="^pay_(?:1day|3days|7days)$"))
    application.add_handler(CallbackQueryHandler(payment_done, pattern="^payment_done_"))
    application.add_handler(CallbackQueryHandler(admin_approve, pattern="^approve_"))
    application.add_handler(CallbackQueryHandler(admin_decline, pattern="^decline_"))
    application.add_handler(CallbackQueryHandler(checkout_start, pattern="^checkout$"))
    application.add_handler(CallbackQueryHandler(profile_dashboard, pattern="^profile$"))
    application.add_handler(CallbackQueryHandler(back_to_start, pattern="^back_to_start$"))

    application.add_handler(MessageHandler(filters.Regex(r'^/approve_\d+_\d+$'), approve_text_command))
    application.add_handler(MessageHandler(filters.Regex(r'^/decline_\d+$'), decline_text_command))

    # Add a single text router for non-command text inputs
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))
    application.add_handler(MessageHandler((filters.PHOTO | filters.Document.ALL) & ~filters.COMMAND, handle_payment_proof))
    application.add_error_handler(error_handler)

    # Ensure an asyncio event loop exists for Python 3.14+ before run_polling
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
    
    # Start bot
    logger.info("🔥 HOTTBOII CHECKOUT BOT STARTED")
    application.run_polling()

if __name__ == "__main__":
    main()