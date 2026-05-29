"""Получение цен (тикеров) со всех бирж через библиотеку ccxt."""
import asyncio
import ccxt.async_support as ccxt
from loguru import logger

from config import EXCHANGES, QUOTE_CURRENCIES, TOP_COINS, REQUEST_TIMEOUT


def _build_symbols() -> set[str]:
    return {f"{coin}/{quote}" for coin in TOP_COINS for quote in QUOTE_CURRENCIES}


SYMBOLS = _build_symbols()


def _create_exchange(name: str):
    exchange_class = getattr(ccxt, name)
    return exchange_class({
        "enableRateLimit": True,
        "timeout": REQUEST_TIMEOUT,
        "options": {
            "defaultType": "spot",
        },
    })


async def _fetch_one(exchange_name: str) -> tuple[str, dict]:
    """Опросить одну биржу: вернуть {symbol: {'bid': float, 'ask': float}}."""
    exchange = _create_exchange(exchange_name)
    result: dict[str, dict] = {}
    try:
        await exchange.load_markets()
        symbols_to_fetch = [s for s in SYMBOLS if s in exchange.markets]
        if symbols_to_fetch:
            tickers = await exchange.fetch_tickers(symbols_to_fetch)
        else:
            tickers = await exchange.fetch_tickers()
        for symbol, ticker in tickers.items():
            if symbol not in SYMBOLS:
                continue
            bid = ticker.get("bid")
            ask = ticker.get("ask")
            if bid and ask and bid > 0 and ask > 0:
                result[symbol] = {"bid": float(bid), "ask": float(ask)}
        logger.info(f"[{exchange_name}] получено {len(result)} тикеров")
    except Exception as e:
        logger.warning(f"[{exchange_name}] ошибка: {e}")
    finally:
        await exchange.close()
    return exchange_name, result


async def fetch_all_tickers() -> dict[str, dict[str, dict]]:
    """Опросить все биржи параллельно.

    Возвращает: {exchange_name: {symbol: {'bid': float, 'ask': float}}}
    """
    tasks = [_fetch_one(name) for name in EXCHANGES]
    results = await asyncio.gather(*tasks)
    return {name: data for name, data in results}
