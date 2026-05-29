"""Информация о биржах: URL-шаблоны торговых страниц и торговые комиссии."""


def _binance_url(base: str, quote: str) -> str:
    return f"https://www.binance.com/en/trade/{base}_{quote}"


def _bybit_url(base: str, quote: str) -> str:
    return f"https://www.bybit.com/en/trade/spot/{base}/{quote}"


def _okx_url(base: str, quote: str) -> str:
    return f"https://www.okx.com/trade-spot/{base.lower()}-{quote.lower()}"


def _kucoin_url(base: str, quote: str) -> str:
    return f"https://www.kucoin.com/trade/{base}-{quote}"


def _gateio_url(base: str, quote: str) -> str:
    return f"https://www.gate.io/trade/{base}_{quote}"


def _mexc_url(base: str, quote: str) -> str:
    return f"https://www.mexc.com/exchange/{base}_{quote}"


EXCHANGE_URLS = {
    "binance": _binance_url,
    "bybit":   _bybit_url,
    "okx":     _okx_url,
    "kucoin":  _kucoin_url,
    "gateio":  _gateio_url,
    "mexc":    _mexc_url,
}

EXCHANGE_DISPLAY_NAMES = {
    "binance": "Binance",
    "bybit":   "Bybit",
    "okx":     "OKX",
    "kucoin":  "KuCoin",
    "gateio":  "Gate.io",
    "mexc":    "MEXC",
}

TAKER_FEES_PERCENT = {
    "binance": 0.10,
    "bybit":   0.10,
    "okx":     0.10,
    "kucoin":  0.10,
    "gateio":  0.20,
    "mexc":    0.10,
}


def trade_url(exchange: str, symbol: str) -> str:
    base, quote = symbol.split("/")
    builder = EXCHANGE_URLS.get(exchange)
    return builder(base, quote) if builder else ""


def display_name(exchange: str) -> str:
    return EXCHANGE_DISPLAY_NAMES.get(exchange, exchange.capitalize())


def taker_fee(exchange: str) -> float:
    return TAKER_FEES_PERCENT.get(exchange, 0.10)
