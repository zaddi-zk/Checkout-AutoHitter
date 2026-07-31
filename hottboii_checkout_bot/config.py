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
BOT_TOKEN = os.getenv("BOT_TOKEN", "8899289220:AAEZmznaurY6w2fQbULdunpBUtW95wLop70")
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
DB_PATH = Path("hottboii.db")

# --- Checkout engine settings ---
# Prefer HEADLESS (new) but keep HEADLESS_CHECKOUT for backward compatibility.
HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"
HEADLESS_CHECKOUT = os.getenv("HEADLESS_CHECKOUT", str(HEADLESS)).lower() == "true"

# Load CAPTCHA_API_KEY - first from env, with hardcoded fallback
CAPTCHA_API_KEY = os.getenv("CAPTCHA_API_KEY", "")
if not CAPTCHA_API_KEY:
    CAPTCHA_API_KEY = "sand-14244b2bfbf329bc60b05d8817a4e50aae16598ed838b3b209318dad58ac8160"

if not CAPTCHA_API_KEY:
    logger.warning("CAPTCHA_API_KEY is empty! CAPTCHA solving will fail.")
else:
    logger.info("CAPTCHA_API_KEY loaded (%d chars)", len(CAPTCHA_API_KEY))

ENGINE_TIMEOUT = int(os.getenv("ENGINE_TIMEOUT", "30"))
PREMIUM_MODE = os.getenv("PREMIUM_MODE", "1") == "1"
CHECKOUT_ENGINE = os.getenv("CHECKOUT_ENGINE", "auto")


# --- 3DS Burp Suite proxy ---
# Set BURP_PROXY to e.g. "http://127.0.0.1:8080" to route Chrome through Burp Suite
# for manual 3DS interception. Set BURP_ENABLED=true to enable.
BURP_PROXY = os.getenv("BURP_PROXY", "")
BURP_ENABLED = os.getenv("BURP_ENABLED", "false").lower() == "true"

# --- Admin list ---
ADMINS = [ADMIN_ID, DEVELOPER_ID, OWNER_ID]