"""Расчёт реальной цены исполнения по стакану (с учётом slippage)."""
import asyncio

import ccxt.async_support as ccxt
from loguru import logger

from config import REQUEST_TIMEOUT


def _create_exchange(name: str):
    exchange_class = getattr(ccxt, name)
    return exchange_class({
        "enableRateLimit": True,
        "timeout": REQUEST_TIMEOUT,
        "options": {"defaultType": "spot"},
    })


async def _fetch_book(exchange_name: str, symbol: str, limit: int = 50) -> dict | None:
    exchange = _create_exchange(exchange_name)
    try:
        return await exchange.fetch_order_book(symbol, limit)
    except Exception as e:
        logger.debug(f"[{exchange_name}] book {symbol} skip: {e}")
        return None
    finally:
        await exchange.close()


def _walk_asks(asks: list, target_quote: float) -> tuple[float, float]:
    """Покупка: набираем монеты пока не потратим target_quote."""
    total_base = 0.0
    total_quote = 0.0
    for price, amount in asks:
        if total_quote >= target_quote:
            break
        need_quote = target_quote - total_quote
        level_quote = price * amount
        if level_quote <= need_quote:
            total_base += amount
            total_quote += level_quote
        else:
            buy_amount = need_quote / price
            total_base += buy_amount
            total_quote += need_quote
            break
    if total_base <= 0:
        return 0.0, 0.0
    avg_price = total_quote / total_base
    return avg_price, total_quote


def _walk_bids(bids: list, target_base: float) -> tuple[float, float]:
    """Продажа: продаём target_base монет по убывающим bids."""
    total_base = 0.0
    total_quote = 0.0
    for price, amount in bids:
        if total_base >= target_base:
            break
        need_base = target_base - total_base
        sell_amount = min(amount, need_base)
        total_base += sell_amount
        total_quote += sell_amount * price
    if total_base <= 0:
        return 0.0, 0.0
    avg_price = total_quote / total_base
    return avg_price, total_base


async def real_execution_prices(
    symbol: str,
    buy_exchange: str,
    sell_exchange: str,
    target_quote_usd: float,
) -> tuple[float, float] | None:
    """Возвращает (avg_buy_price, avg_sell_price) с учётом стакана,
    либо None если ликвидности не хватает."""
    buy_book, sell_book = await asyncio.gather(
        _fetch_book(buy_exchange, symbol),
        _fetch_book(sell_exchange, symbol),
    )
    if not buy_book or not sell_book:
        return None
    asks = buy_book.get("asks") or []
    bids = sell_book.get("bids") or []
    if not asks or not bids:
        return None

    avg_buy, bought_quote = _walk_asks(asks, target_quote_usd)
    if avg_buy <= 0 or bought_quote < target_quote_usd * 0.8:
        return None

    base_bought = bought_quote / avg_buy
    avg_sell, sold_base = _walk_bids(bids, base_bought)
    if avg_sell <= 0 or sold_base < base_bought * 0.8:
        return None

    return avg_buy, avg_sell
