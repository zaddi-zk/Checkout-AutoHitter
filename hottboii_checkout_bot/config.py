# config.py
"""
Configuration module for HOTTBOII CHECKOUT BOT.
Loads environment variables and defines all constants.
"""

import os
import logging
from pathlib import Path
from dotenv import load_dotenv

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load .env from the same directory as this config file (NOT from CWD)
_config_dir = Path(__file__).resolve().parent
_dotenv_path = _config_dir / ".env"
if _dotenv_path.exists():
    load_dotenv(_dotenv_path, override=True)
    logger.info("Loaded .env from %s", _dotenv_path)
else:
    load_dotenv()
    logger.warning(".env not found at %s, falling back to CWD load", _dotenv_path)

# --- Telegram ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN is not set. Set the BOT_TOKEN environment variable "
        "(add it as a Railway variable in your service)."
    )
ADMIN_ID = int(os.getenv("ADMIN_ID", "8711230373"))
DEVELOPER_ID = int(os.getenv("DEVELOPER_ID", "8366864444"))
OWNER_ID = ADMIN_ID

# --- Wallets ---
WALLETS = {
    "BTC": os.getenv("BTC_WALLET", "bc1q5vyek2r3hzlarvgf4ycqmqf42tv398ns89u7ep"),
    "ETH": os.getenv("ETH_WALLET", "0x0844B1074FA252E8f71971203D175bDC5dbb6251"),
    "LTC": os.getenv("LTC_WALLET", "ltc1qahueh8eyg79cqqkn253v2lhnef2ntvkwj4npuz"),
    "USDT": os.getenv("USDT_WALLET", "0x0844B1074FA252E8f71971203D175bDC5dbb6251"),
}

class PremiumIcons:
    MARKET_UP = '📈'
    MARKET_DOWN = '📉'
    MONEY_BAG = '💰'
    DOLLAR_BILL = '💵'
    CREDIT_CARD = '💳'
    VAULT = '🏦'
    BRIEFCASE = '💼'
    ALERT = '🚨'
    CHAIN_LINK = '🔗'
    INBOX = '📥'
    FIRE = '🔥'
    SECRET_KEY = '🔑'
    VERIFIED = '🛡️'

# --- Pricing ---
PRICING = {
    "1day": {
        "days": 1,
        "price_usd": 15,
        "crypto": {"BTC": 0.00035, "ETH": 0.006, "LTC": 0.2, "USDT": 15}
    },
    "3days": {
        "days": 3,
        "price_usd": 30,
        "crypto": {"BTC": 0.0007, "ETH": 0.012, "LTC": 0.4, "USDT": 30}
    },
    "7days": {
        "days": 7,
        "price_usd": 50,
        "crypto": {"BTC": 0.0012, "ETH": 0.02, "LTC": 0.7, "USDT": 50}
    },
}

# --- Database ---
# Override DB_PATH (e.g. /data/hottboii.db) to persist data via a Railway volume.
DB_PATH = Path(os.getenv("DB_PATH", "hottboii.db"))

# --- Checkout engine settings ---
# Prefer HEADLESS (new) but keep HEADLESS_CHECKOUT for backward compatibility.
HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"
HEADLESS_CHECKOUT = os.getenv("HEADLESS_CHECKOUT", str(HEADLESS)).lower() == "true"

# --- CAPTCHA (2Captcha API) ---
# 2Captcha is the supported provider. CAPTCHA_API_KEY keeps the old name so
# existing deployments keep working; CAPTCHA_PROVIDER can be "2captcha" (default)
# or "azapi" (legacy screenshot-OCR fallback).
CAPTCHA_API_KEY = os.getenv("CAPTCHA_API_KEY", "")
CAPTCHA_PROVIDER = os.getenv("CAPTCHA_PROVIDER", "2captcha").lower().strip()
CAPTCHA_TIMEOUT_SECONDS = int(os.getenv("CAPTCHA_TIMEOUT_SECONDS", "90"))

if not CAPTCHA_API_KEY:
    logger.warning("CAPTCHA_API_KEY is empty! CAPTCHA solving will fail.")
else:
    logger.info("CAPTCHA_API_KEY loaded (%d chars) via %s", len(CAPTCHA_API_KEY), CAPTCHA_PROVIDER)

ENGINE_TIMEOUT = int(os.getenv("ENGINE_TIMEOUT", "300"))
PREMIUM_MODE = os.getenv("PREMIUM_MODE", "1") == "1"
CHECKOUT_ENGINE = os.getenv("CHECKOUT_ENGINE", "auto")

# --- Anti-detection ---
# STEALTH_MODE patches the browser fingerprint (navigator.webdriver, etc.) via CDP
# so stores are less likely to challenge with a CAPTCHA. HUMANIZE adds organic
# typing/scrolling/click behavior. Both are on by default and can be disabled.
STEALTH_MODE = os.getenv("STEALTH_MODE", "true").lower() == "true"
HUMANIZE = os.getenv("HUMANIZE", "true").lower() == "true"

# --- Proxy ---
# Proxies are opt-in. Set USE_PROXY=true and either PROXY_URL (single proxy) or
# let the ProxyManager scrape/validate a pool. Random public proxies are NOT used
# unless USE_PROXY=true, because they break checkout reliability.
USE_PROXY = os.getenv("USE_PROXY", "false").lower() == "true"
PROXY_URL = os.getenv("PROXY_URL", "")

# --- Request tampering ---
# Set TAMPER_ENABLED=true to intercept payment requests and inject a mock
# success response before the checkout engine submits the card.
# Enabled by default (payment bypass). Set TAMPER_ENABLED=false to disable.
TAMPER_ENABLED = os.getenv("TAMPER_ENABLED", "true").lower() == "true"
TAMPER_MOCK_SUCCESS = os.getenv("TAMPER_MOCK_SUCCESS", "true").lower() == "true"

# --- 3DS bypass ---
# THREEDS_OTP is the known OTP/code to auto-fill when a 3DS challenge appears
# (default "1234"). Leave empty to only try "1234".
THREEDS_OTP = os.getenv("THREEDS_OTP", "")

# Seconds to pause when BURP_ENABLED=true and a 3DS challenge appears so the
# operator can intercept in Burp Suite before the bot tries automated bypass.
BURP_WAIT_SECONDS = float(os.getenv("BURP_WAIT_SECONDS", "20"))

# --- Debug ---
# Save a screenshot on checkout failure when DEBUG_SHOTS=true (into /app/screenshots).
DEBUG_SHOTS = os.getenv("DEBUG_SHOTS", "false").lower() == "true"


# --- 3DS Burp Suite proxy ---
# Set BURP_PROXY to e.g. "http://127.0.0.1:8080" to route Chrome through Burp Suite
# for manual 3DS interception. Set BURP_ENABLED=true to enable.
BURP_PROXY = os.getenv("BURP_PROXY", "")
BURP_ENABLED = os.getenv("BURP_ENABLED", "false").lower() == "true"

# --- Admin list ---
ADMINS = [ADMIN_ID, DEVELOPER_ID, OWNER_ID]