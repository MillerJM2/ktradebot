"""Конфигурация бота: настройки бирж, монет, порогов."""
import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_TELEGRAM_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "0"))

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///bot.db")

EXCHANGES = ["binance", "bybit", "okx", "kucoin", "gateio", "mexc"]

QUOTE_CURRENCIES = ["USDT", "BTC"]

DEFAULT_SPREAD_THRESHOLD = 2.0

MAX_SPREAD_PERCENT = 20.0

MIN_QUOTE_VOLUME_USD = 10_000

POLL_INTERVAL_SECONDS = 30

REQUEST_TIMEOUT = 20000
