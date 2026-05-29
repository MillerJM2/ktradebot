"""Получение цен (тикеров) со всех бирж через библиотеку ccxt."""
import asyncio
import ccxt.async_support as ccxt
from loguru import logger

from config import (
    EXCHANGES,
    MIN_QUOTE_VOLUME_USD,
    QUOTE_CURRENCIES,
    REQUEST_TIMEOUT,
)


def _is_target_symbol(symbol: str) -> bool:
    """Принимаем любые пары с USDT или BTC в качестве котировки (FOO/USDT, FOO/BTC)."""
    if "/" not in symbol:
        return False
    base, quote = symbol.split("/", 1)
    if ":" in quote:
        return False
    return quote in QUOTE_CURRENCIES


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
    """Опросить одну биржу: вернуть {symbol: {'bid', 'ask', 'quote_volume'}}."""
    exchange = _create_exchange(exchange_name)
    result: dict[str, dict] = {}
    skipped_low_volume = 0
    try:
        tickers = await exchange.fetch_tickers()
        for symbol, ticker in tickers.items():
            if not _is_target_symbol(symbol):
                continue
            bid = ticker.get("bid")
            ask = ticker.get("ask")
            if not (bid and ask and bid > 0 and ask > 0):
                continue
            quote_vol = ticker.get("quoteVolume") or 0
            base, quote = symbol.split("/", 1)
            quote_vol_usd = float(quote_vol) if quote == "USDT" else float(quote_vol) * float(ask)
            if quote_vol_usd < MIN_QUOTE_VOLUME_USD:
                skipped_low_volume += 1
                continue
            result[symbol] = {
                "bid": float(bid),
                "ask": float(ask),
                "quote_volume": quote_vol_usd,
            }
        logger.info(
            f"[{exchange_name}] получено {len(result)} тикеров "
            f"(отфильтровано по объёму: {skipped_low_volume})"
        )
    except Exception as e:
        logger.warning(f"[{exchange_name}] ошибка: {e}")
    finally:
        await exchange.close()
    return exchange_name, result


async def fetch_all_tickers() -> dict[str, dict[str, dict]]:
    """Опросить все биржи параллельно.

    Возвращает: {exchange_name: {symbol: {'bid', 'ask', 'quote_volume'}}}
    """
    tasks = [_fetch_one(name) for name in EXCHANGES]
    results = await asyncio.gather(*tasks)
    return {name: data for name, data in results}
