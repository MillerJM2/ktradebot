"""Конфигурация бота: настройки бирж, монет, порогов."""
import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_TELEGRAM_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "0"))

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///bot.db")

CRYPTOBOT_API_TOKEN = os.getenv("CRYPTOBOT_API_TOKEN", "")
CRYPTOBOT_BASE_URL = os.getenv(
    "CRYPTOBOT_BASE_URL", "https://pay.crypt.bot/api"
)
INVOICE_POLL_INTERVAL_SECONDS = 30
PROMO_UNTIL_DATE = "12.03.2026"

REFERRAL_PERCENT = 20
MIN_WITHDRAW_USD = 5.0

EXPIRY_CHECK_INTERVAL_SECONDS = 3600

CHANNEL_URL = "https://t.me/cryptosyndicate33"
CHANNEL_NAME = "Crypto Syndicate"

EXCHANGES = [
    "binance", "bybit", "okx", "kucoin", "gateio", "mexc",
    "bitget", "bingx", "htx", "bitfinex",
]

QUOTE_CURRENCIES = ["USDT", "BTC"]

DEFAULT_SPREAD_THRESHOLD = 1.5

MAX_SPREAD_PERCENT = 30.0

MIN_QUOTE_VOLUME_USD = 10_000

MIN_PROFIT_PERCENT = 1.5
MAX_PROFIT_PERCENT = 10.0
TARGET_AMOUNT_USD = 1000.0

POLL_INTERVAL_SECONDS = 30
CURRENCIES_REFRESH_SECONDS = 300
MAX_CANDIDATES_FOR_VERIFY = 40

REQUEST_TIMEOUT = 20000

# ── Авто-трейдер ──────────────────────────────────────────────────────────────
TRADER_ENABLED = os.getenv("TRADER_ENABLED", "false").lower() == "true"
TRADER_AMOUNT_USD = float(os.getenv("TRADER_AMOUNT_USD", "200"))
TRADER_MIN_PROFIT_PCT = float(os.getenv("TRADER_MIN_PROFIT_PCT", "1.5"))
TRADER_MAX_DAILY_TRADES = int(os.getenv("TRADER_MAX_DAILY_TRADES", "10"))
TRADER_MAX_DAILY_LOSS_USD = float(os.getenv("TRADER_MAX_DAILY_LOSS_USD", "100"))

BYBIT_API_KEY = os.getenv("BYBIT_API_KEY", "")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET", "")

BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")

OKX_API_KEY = os.getenv("OKX_API_KEY", "")
OKX_API_SECRET = os.getenv("OKX_API_SECRET", "")
OKX_PASSPHRASE = os.getenv("OKX_PASSPHRASE", "")
