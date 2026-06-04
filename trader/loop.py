"""Логика авто-трейдера: проверка условий и исполнение арбитражных сделок."""
import asyncio
from typing import Callable, Coroutine, Optional

from loguru import logger

from .accounts import TraderAccounts
from .executor import TradeExecutor
from arbitrage.exchange_info import taker_fee


_trader_instance: Optional["AutoTrader"] = None


def get_trader() -> Optional["AutoTrader"]:
    return _trader_instance


def set_trader(t: "AutoTrader") -> None:
    global _trader_instance
    _trader_instance = t


class AutoTrader:
    def __init__(self, accounts: TraderAccounts):
        self.accounts = accounts
        self.executor = TradeExecutor(accounts)
        self._enabled = False
        self._active: set[str] = set()
        self._lock = asyncio.Lock()

    # ── state ─────────────────────────────────────────────────────────────────

    def is_enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, value: bool) -> None:
        self._enabled = value
        logger.info(f"AutoTrader {'включён' if value else 'выключен'}")

    # ── main entry ─────────────────────────────────────────────────────────────

    async def process_spreads(
        self,
        spreads,  # list[VerifiedSpread] — не импортируем во избежание циклов
        notify: Optional[Callable[[str], Coroutine]] = None,
    ) -> None:
        if not self._enabled:
            return

        from config import (
            TRADER_AMOUNT_USD,
            TRADER_MIN_PROFIT_PCT,
            TRADER_MAX_DAILY_TRADES,
            TRADER_MAX_DAILY_LOSS_USD,
        )
        from database.trades_repo import get_daily_stats

        trader_exchanges = set(self.accounts.enabled_exchanges())
        candidates = [
            s for s in spreads
            if s.buy_exchange in trader_exchanges
            and s.sell_exchange in trader_exchanges
            and s.net_profit_percent >= TRADER_MIN_PROFIT_PCT
        ]
        if not candidates:
            return

        stats = await get_daily_stats()
        if stats["trade_count"] >= TRADER_MAX_DAILY_TRADES:
            logger.warning("AutoTrader: дневной лимит сделок достигнут")
            return
        if stats["net_profit"] <= -abs(TRADER_MAX_DAILY_LOSS_USD):
            logger.warning("AutoTrader: дневной лимит убытков достигнут")
            return

        # Берём лучшую возможность
        best = candidates[0]
        await self._try_execute(best, TRADER_AMOUNT_USD, notify)

    # ── execution ──────────────────────────────────────────────────────────────

    async def _try_execute(self, spread, amount_usdt: float, notify) -> None:
        from config import TRADER_AMOUNT_USD
        pair_key = f"{spread.symbol}:{spread.buy_exchange}:{spread.sell_exchange}"

        async with self._lock:
            if pair_key in self._active:
                return
            self._active.add(pair_key)

        try:
            coin = spread.symbol.split("/")[0]

            buy_bal = await self.accounts.fetch_balance(spread.buy_exchange)
            sell_bal = await self.accounts.fetch_balance(spread.sell_exchange)

            if buy_bal.usdt < amount_usdt:
                logger.info(
                    f"AutoTrader: мало USDT на {spread.buy_exchange}: "
                    f"{buy_bal.usdt:.2f} < {amount_usdt}"
                )
                return

            coin_needed = amount_usdt / spread.book_buy_price
            coin_available = sell_bal.coin(coin)
            if coin_available < coin_needed * 0.9:
                logger.info(
                    f"AutoTrader: мало {coin} на {spread.sell_exchange}: "
                    f"{coin_available:.6f} < {coin_needed:.6f}"
                )
                return

            logger.info(
                f"AutoTrader: исполняю {spread.symbol} "
                f"{spread.buy_exchange}→{spread.sell_exchange} "
                f"ожид.профит={spread.net_profit_percent:.2f}%"
            )

            buy_order, sell_order = await self.executor.execute_arb(
                symbol=spread.symbol,
                buy_exchange=spread.buy_exchange,
                sell_exchange=spread.sell_exchange,
                usdt_amount=amount_usdt,
            )

            # Вычисляем реальный P&L
            buy_price = buy_order.avg_price if buy_order else 0.0
            sell_price = sell_order.avg_price if sell_order else 0.0
            amount_coin = buy_order.amount_coin if buy_order else 0.0
            buy_cost = buy_order.amount_usdt if buy_order else amount_usdt
            sell_proceeds = sell_order.amount_usdt if sell_order else 0.0

            buy_fee = buy_cost * taker_fee(spread.buy_exchange) / 100
            sell_fee = sell_proceeds * taker_fee(spread.sell_exchange) / 100
            trade_fees = buy_fee + sell_fee

            gross_profit = sell_proceeds - buy_cost
            net_profit = gross_profit - trade_fees

            status = "completed" if (buy_order and sell_order) else "failed"
            error_msg = None
            if not buy_order:
                error_msg = "buy failed"
            elif not sell_order:
                error_msg = "sell failed"

            from database.trades_repo import create_trade
            await create_trade(
                symbol=spread.symbol,
                buy_exchange=spread.buy_exchange,
                sell_exchange=spread.sell_exchange,
                amount_usdt=amount_usdt,
                buy_price=buy_price,
                sell_price=sell_price,
                amount_coin=amount_coin,
                gross_profit_usd=gross_profit,
                trade_fees_usd=trade_fees,
                net_profit_usd=net_profit,
                status=status,
                error_msg=error_msg,
            )

            if notify:
                sign = "✅" if net_profit > 0 else ("⚠️" if status == "failed" else "❌")
                await notify(
                    f"{sign} <b>Авто-трейд: {spread.symbol}</b>\n"
                    f"{spread.buy_exchange} → {spread.sell_exchange}\n"
                    f"Размер: <b>${amount_usdt:,.0f}</b>\n"
                    f"Покупка: {buy_price:.4f}$ | Продажа: {sell_price:.4f}$\n"
                    f"Профит: <b>{net_profit:+.2f} USDT</b>"
                    + (f"\n⚠️ {error_msg}" if error_msg else "")
                )
        finally:
            async with self._lock:
                self._active.discard(pair_key)
