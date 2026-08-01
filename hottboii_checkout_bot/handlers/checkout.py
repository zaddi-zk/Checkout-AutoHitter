# handlers/checkout.py
"""
Main checkout logic – URL, shipping, cards, and processing.
"""

import asyncio
from datetime import datetime
from typing import Any, cast

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup

from telegram.ext import ContextTypes

from checkout_runner import run_checkout_with_fallback
from config import HEADLESS_CHECKOUT, PremiumIcons, ADMINS



from database import get_active_key, log_checkout_attempt


# ---------- START CHECKOUT ----------


async def checkout_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Initiate checkout – verify premium key first."""
    query = update.callback_query
    if query is None:
        return

    user = update.effective_user
    if user is None:
        return

    await query.answer()

    # Admins bypass key check
    if user.id in ADMINS:
        await query.edit_message_text(
            f"{PremiumIcons.CREDIT_CARD} <b>Checkout Mode</b>\n\n"
            "Please provide the checkout URL:\n\n"
            "📌 <i>Share the product URL from your browser.</i>\n"
            "📌 <i>Works with Shopify, Stripe, and WooCommerce.</i>",
            parse_mode="HTML"
        )
        if context.user_data is not None:
            context.user_data['checkout_step'] = 'waiting_url'
        return

    # Check active key
    active_key = get_active_key(user.id)
    if not active_key:
        await query.edit_message_text(
            f"{PremiumIcons.ALERT} <b>Access Required</b>\n\n"
            "You need a premium key to use the checkout bot.\n\n"
            "Use <code>/getkey</code> to purchase one.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(f"{PremiumIcons.SECRET_KEY} Get Key", callback_data="get_key")],
                [InlineKeyboardButton("◀️ Back", callback_data="back_to_start")]
            ])
        )
        return

    # Check expiry
    expires_at = active_key.get('expires_at')
    if expires_at and datetime.fromisoformat(expires_at) < datetime.now():
        await query.edit_message_text(
            f"{PremiumIcons.ALERT} <b>Key Expired</b>\n\n"
            "Your premium key has expired.\n\n"
            "Please purchase a new key.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(f"{PremiumIcons.SECRET_KEY} Get Key", callback_data="get_key")],
                [InlineKeyboardButton("◀️ Back", callback_data="back_to_start")]
            ])
        )
        return

    await query.edit_message_text(
        f"{PremiumIcons.CREDIT_CARD} <b>Checkout Mode</b>\n\n"
        "Please provide the checkout URL:\n\n"
        "📌 <i>Share the product URL from your browser.</i>\n"
        "📌 <i>Works with Shopify, Stripe, and WooCommerce.</i>",
        parse_mode="HTML"
    )

    user_data = context.user_data
    if user_data is None:
        return

    user_data['checkout_step'] = 'waiting_url'


# ---------- HANDLE URL ----------

async def handle_checkout_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Store checkout URL."""
    message = update.message
    if message is None or message.text is None:
        return

    url = message.text.strip()
    if not url.startswith(('http://', 'https://')):
        await message.reply_text("❌ Invalid URL. Please provide a valid checkout URL.")
        return

    user_data = context.user_data
    if user_data is None:
        return

    user_data['checkout_url'] = url
    user_data['checkout_step'] = 'waiting_shipping'

    await message.reply_text(
        f"{PremiumIcons.VAULT} <b>URL Saved</b>\n\n"
        "Now provide your <b>shipping details</b> and <b>email</b>.\n\n"
        "Enter each line, one at a time:\n"
        "<pre>\n"
        "John Smith\n"
        "1234 Beverly Lane\n"
        "Chino Hills\n"
        "CA\n"
        "93277\n"
        "getmycheckout@gmail.com\n"
        "</pre>\n\n"
        "ℹ️ <i>Optional 7th line = phone number (needed by some stores).</i>\n"
        "❗ <i>Use this exact format for best results.</i>",
        parse_mode="HTML"
    )


# ---------- HANDLE SHIPPING ----------

async def handle_shipping_line(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Collect shipping details line by line."""
    user_data = context.user_data
    if user_data is None:
        return
    if user_data.get('checkout_step') != 'waiting_shipping':
        return
    message = update.message
    if message is None or message.text is None:
        return
    text = message.text.strip()

    shipping_lines = user_data.get('shipping_lines')
    if not isinstance(shipping_lines, list):
        shipping_lines = []
        user_data['shipping_lines'] = shipping_lines

    phone = None

    if "\n" in text:
        parts = [p.strip() for p in text.splitlines() if p.strip()]
        if len(parts) >= 7:
            lines = parts[:6]
            phone = parts[6]
        elif len(parts) == 6:
            lines = parts
        else:
            shipping_lines.extend(parts)
            remaining = 6 - len(shipping_lines)
            if remaining > 0:
                await message.reply_text(
                    f"{PremiumIcons.INBOX} <b>Line received</b>: <code>{parts[-1]}</code>\n"
                    f"📊 {remaining} more line(s) needed.\n\n"
                    f"Current lines: {len(shipping_lines)}/6",
                    parse_mode="HTML"
                )
                return
            lines = shipping_lines
    else:
        if len(shipping_lines) < 6:
            shipping_lines.append(text)
            remaining = 6 - len(shipping_lines)
            await message.reply_text(
                f"{PremiumIcons.INBOX} <b>Line received</b>: <code>{text}</code>\n"
                f"📊 {remaining} more line(s) needed.\n\n"
                f"Current lines: {len(shipping_lines)}/6",
                parse_mode="HTML"
            )
            return
        # Already have the 6 required lines — treat this as the optional phone.
        phone = text
        lines = shipping_lines

    if len(lines) != 6:
        await message.reply_text("❌ You need exactly 6 lines. Please start over with /start")
        user_data['shipping_lines'] = []
        return

    user_data['shipping'] = {
        'full_name': lines[0],
        'address': lines[1],
        'city': lines[2],
        'state': lines[3],
        'zip': lines[4],
        'email': lines[5],
        'phone': phone or '',
    }
    user_data['checkout_step'] = 'waiting_cards'
    user_data.pop('shipping_lines', None)

    await message.reply_text(
        f"{PremiumIcons.CREDIT_CARD} <b>Shipping Details Saved</b>\n\n"
        "Now provide the <b>credit cards</b> you want to use.\n\n"
        "Format (one per line):\n"
        "<pre>\n"
        "4966840010352295|06|28|133|Joseph Corral|540 Brinkby Ave|Reno|Nevada|89509\n"
        "701320029329006|10|30|159|Leonel E Hansack chow|13215 HWY 99 S||Everett|WA|98204|\n"
        "</pre>\n\n"
        "❗ <i>The bot will try each card until one works.</i>",
        parse_mode="HTML"
    )


# ---------- HANDLE CARDS ----------

async def handle_cards(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Parse and store card list."""
    user_data = context.user_data
    if user_data is None:
        return

    if user_data.get('checkout_step') != 'waiting_cards':
        return

    message = update.message
    if message is None or message.text is None:
        return

    cards_text = message.text.strip()
    cards: list[dict[str, str]] = []
    for line in cards_text.split('\n'):
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split('|')]
        # Allow common paste format where expiry is "MM/YY" in a single field
        # Expected canonical parts: number|exp_month|exp_year|cvv|name|address|city|state|zip
        if len(parts) == 8:
            exp = parts[1]
            if '/' in exp:
                try:
                    m, y = [s.strip() for s in exp.split('/', 1)]
                    parts = [parts[0], m, y, parts[2], parts[3], parts[4], parts[5], parts[6], parts[7]]
                except Exception:
                    pass
        if len(parts) >= 9:
            cards.append({
                'number': parts[0].strip(),
                'exp_month': parts[1].strip(),
                'exp_year': parts[2].strip(),
                'cvv': parts[3].strip(),
                'name': parts[4].strip() if len(parts) > 4 else '',
                'address': parts[5].strip() if len(parts) > 5 else '',
                'city': parts[6].strip() if len(parts) > 6 else '',
                'state': parts[7].strip() if len(parts) > 7 else '',
                'zip': parts[8].strip() if len(parts) > 8 else '',
            })
        else:
            await message.reply_text(
                f"{PremiumIcons.ALERT} <b>Invalid format:</b> <code>{line}</code>\n\n"
                "Expected: <code>number|exp_month|exp_year|cvv|name|address|city|state|zip</code>",
                parse_mode="HTML"
            )
            return

    if not cards:
        await message.reply_text("❌ No valid cards found. Please try again.")
        return

    context.user_data['cards'] = cards
    context.user_data['checkout_step'] = 'processing'

    await message.reply_text(
        f"{PremiumIcons.FIRE} <b>Cards Loaded</b>\n\n"
        f"📊 Total cards: {len(cards)}\n"
        f"🚀 Starting checkout process...\n\n"
        "This may take a few minutes. You will be notified when done.",
        parse_mode="HTML"
    )

    await process_checkout(update, context)


# ---------- PROCESS CHECKOUT (INTEGRATED WITH RUNNER) ----------

async def process_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process checkout using the runner with engine fallback and CAPTCHA support."""
    user_data = context.user_data
    if user_data is None:
        return

    message = update.message or update.callback_query
    if message is None:
        return

    cards = cast(list[dict[str, Any]], user_data.get('cards', []))
    if not cards:
        await (message.reply_text if hasattr(message, 'reply_text') else update.effective_message.reply_text)("❌ No cards to process.")
        return

    shipping = user_data.get('shipping', {})
    url = user_data.get('checkout_url', '')
    if not url:
        await (message.reply_text if hasattr(message, 'reply_text') else update.effective_message.reply_text)("❌ Checkout URL missing. Start over.")
        return

    async def send_progress(msg: str):
        try:
            await update.effective_message.reply_text(msg)
        except Exception:
            pass

    # Run the blocking runner in a threadpool. Progress updates are scheduled on
    # the main loop WITHOUT blocking the worker thread (no .result()).
    main_loop = asyncio.get_event_loop()

    def _push_progress(msg: str):
        try:
            main_loop.call_soon_threadsafe(asyncio.ensure_future, send_progress(msg))
        except Exception:
            pass

    result = await main_loop.run_in_executor(
        None,
        run_checkout_with_fallback,
        url,
        shipping,
        cards,
        _push_progress,
        HEADLESS_CHECKOUT,
        None,  # CAPTCHA is solved automatically by engines (2Captcha)
    )


    user = update.effective_user
    card_bin = ""
    card_last4 = ""
    if cards:
        first_num = cards[0].get("number", "")
        if len(first_num) >= 6:
            card_bin = first_num[:6]
        if len(first_num) >= 4:
            card_last4 = first_num[-4:]
    if user:
        log_checkout_attempt(user.id, url, card_bin, card_last4, result.get("status", "failed"), result.get("message", ""))

    if result.get('status') == 'success':
        await update.effective_message.reply_text(
            "✅ Checkout Completed!\n\n"
            "🎉 Order confirmed! Please check your email.\n"
            "Send vouches to @hottboiihitzz!"
        )
    else:
        await update.effective_message.reply_text(
            f"❌ Checkout Failed\n\n{result.get('message', 'Unknown error')}"
        )

