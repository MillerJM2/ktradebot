"""Исполнение рыночных ордеров на двух биржах одновременно."""
import asyncio
from dataclasses import dataclass
from typing import Optional

from loguru import logger

from .accounts import TraderAccounts


@dataclass
class FilledOrder:
    exchange_id: str
    symbol: str
    side: str           # "buy" | "sell"
    amount_coin: float
    amount_usdt: float
    avg_price: float
    order_id: str


class TradeExecutor:
    def __init__(self, accounts: TraderAccounts):
        self.accounts = accounts

    async def market_buy(
        self, exchange_id: str, symbol: str, usdt_amount: float
    ) -> Optional[FilledOrder]:
        """Покупает монету на сумму usdt_amount. Возвращает FilledOrder или None."""
        ex = self.accounts.get_exchange(exchange_id)
        try:
            if not ex.markets:
                await ex.load_markets()
            ticker = await ex.fetch_ticker(symbol)
            ask = float(ticker.get("ask") or ticker.get("last") or 1)
            base_amount = usdt_amount / ask
            amount_str = ex.amount_to_precision(symbol, base_amount)
            order = await ex.create_market_buy_order(symbol, float(amount_str))
            avg = float(order.get("average") or order.get("price") or ask)
            filled = float(order.get("filled") or base_amount)
            cost = float(order.get("cost") or usdt_amount)
            if avg == 0 and filled > 0:
                avg = cost / filled
            logger.info(
                f"BUY {symbol} on {exchange_id}: "
                f"{filled:.6f} @ {avg:.4f} = {cost:.2f} USDT [#{order.get('id', '?')}]"
            )
            return FilledOrder(
                exchange_id=exchange_id,
                symbol=symbol,
                side="buy",
                amount_coin=filled,
                amount_usdt=cost,
                avg_price=avg,
                order_id=str(order.get("id", "")),
            )
        except Exception as e:
            logger.error(f"market_buy [{exchange_id}] {symbol}: {e}")
            return None

    async def market_sell(
        self, exchange_id: str, symbol: str, coin_amount: float
    ) -> Optional[FilledOrder]:
        """Продаёт coin_amount монет по рынку. Возвращает FilledOrder или None."""
        ex = self.accounts.get_exchange(exchange_id)
        try:
            if not ex.markets:
                await ex.load_markets()
            amount_str = ex.amount_to_precision(symbol, coin_amount)
            order = await ex.create_market_sell_order(symbol, float(amount_str))
            avg = float(order.get("average") or order.get("price") or 0)
            filled = float(order.get("filled") or coin_amount)
            cost = float(order.get("cost") or 0)
            if avg == 0 and filled > 0:
                avg = cost / filled
            logger.info(
                f"SELL {symbol} on {exchange_id}: "
                f"{filled:.6f} @ {avg:.4f} = {cost:.2f} USDT [#{order.get('id', '?')}]"
            )
            return FilledOrder(
                exchange_id=exchange_id,
                symbol=symbol,
                side="sell",
                amount_coin=filled,
                amount_usdt=cost,
                avg_price=avg,
                order_id=str(order.get("id", "")),
            )
        except Exception as e:
            logger.error(f"market_sell [{exchange_id}] {symbol}: {e}")
            return None

    async def execute_arb(
        self,
        symbol: str,
        buy_exchange: str,
        sell_exchange: str,
        usdt_amount: float,
    ) -> tuple[Optional[FilledOrder], Optional[FilledOrder]]:
        """
        Одновременно покупает на buy_exchange и продаёт на sell_exchange.
        Sell exchange должен иметь монету заранее (pre-funded модель).
        Возвращает (buy_order, sell_order) — каждый может быть None.
        """
        sell_ex = self.accounts.get_exchange(sell_exchange)
        if not sell_ex.markets:
            await sell_ex.load_markets()
        ticker = await sell_ex.fetch_ticker(symbol)
        bid = float(ticker.get("bid") or ticker.get("last") or 1)
        coin_amount = usdt_amount / bid

        buy_task = self.market_buy(buy_exchange, symbol, usdt_amount)
        sell_task = self.market_sell(sell_exchange, symbol, coin_amount)
        buy_order, sell_order = await asyncio.gather(buy_task, sell_task)
        return buy_order, sell_order
