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
SUBSCRIPTION_DAYS = 30
INVOICE_POLL_INTERVAL_SECONDS = 30

EXCHANGES = ["binance", "bybit", "okx", "kucoin", "gateio", "mexc"]

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
