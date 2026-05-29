"""Конфигурация бота: настройки бирж, монет, порогов."""
import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_TELEGRAM_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "0"))

EXCHANGES = ["binance", "bybit", "okx", "kucoin", "gateio", "mexc"]

QUOTE_CURRENCIES = ["USDT", "BTC"]

TOP_COINS = [
    "BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "TRX", "TON", "AVAX",
    "DOT", "LINK", "MATIC", "SHIB", "LTC", "BCH", "UNI", "ATOM", "XLM", "ETC",
    "NEAR", "APT", "FIL", "ARB", "OP", "INJ", "SUI", "TIA", "SEI", "RNDR",
    "IMX", "STX", "GRT", "AAVE", "MKR", "ALGO", "QNT", "HBAR", "VET", "EGLD",
    "FLOW", "SAND", "MANA", "AXS", "CHZ", "GALA", "APE", "RUNE", "PEPE", "WIF",
    "FET", "AR", "FTM", "ENS", "DYDX", "JUP", "BONK", "FLOKI", "PYTH", "JTO",
    "STRK", "ORDI", "BLUR", "ICP", "KAS", "TAO", "WLD", "NOT", "MEME", "BOME",
    "ENA", "ETHFI", "W", "WIF", "PIXEL", "PORTAL", "ALT", "MANTA", "DYM", "AEVO",
    "REI", "ZK", "IO", "ZRO", "G", "RENDER", "FTT", "RAY", "JASMY", "OMG",
    "1INCH", "COMP", "SNX", "CRV", "SUSHI", "YFI", "BAT", "ZIL", "ICX", "DASH",
]

DEFAULT_SPREAD_THRESHOLD = 2.0

POLL_INTERVAL_SECONDS = 30

REQUEST_TIMEOUT = 20000
