"""Авто-трейдер: умный выбор сделок с учётом баланса портфеля."""
import asyncio
from typing import Callable, Coroutine, Optional

from loguru import logger

from .accounts import TraderAccounts, ExchangeBalance
from .executor import TradeExecutor
from .portfolio import PortfolioManager
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
        self._portfolio: Optional[PortfolioManager] = None
        self._portfolio_initialized = False

    # ── state ──────────────────────────────────────────────────────────────────

    def is_enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, value: bool) -> None:
        self._enabled = value
        logger.info(f"AutoTrader {'включён' if value else 'выключен'}")

    def get_portfolio(self) -> Optional[PortfolioManager]:
        return self._portfolio

    # ── portfolio init ─────────────────────────────────────────────────────────

    async def _ensure_portfolio(self) -> None:
        """Инициализирует PortfolioManager при первом запуске."""
        if self._portfolio_initialized:
            return
        from config import TRADER_AMOUNT_USD

        exchanges = self.accounts.enabled_exchanges()
        self._portfolio = PortfolioManager(
            exchanges=exchanges,
            target_usdt_per_exchange=TRADER_AMOUNT_USD * 2,  # держим 2 торговых суммы на бирже
            min_usdt_reserve=TRADER_AMOUNT_USD * 0.25,
        )
        try:
            balances = await self.accounts.fetch_all_balances()
            self._portfolio.auto_set_targets_from_balances(balances)
            logger.info("Portfolio Manager инициализирован по текущим балансам")
        except Exception as e:
            logger.warning(f"Не удалось инициализировать portfolio targets: {e}")
        self._portfolio_initialized = True

    # ── main entry ─────────────────────────────────────────────────────────────

    async def process_spreads(
        self,
        spreads,  # list[VerifiedSpread]
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
            logger.warning("AutoTrader: дневной стоп-лосс достигнут")
            return

        await self._ensure_portfolio()

        # Получаем актуальные балансы один раз
        balances = await self.accounts.fetch_all_balances()

        # Уведомляем о критических дисбалансах
        if self._portfolio and notify:
            warnings = self._portfolio.check_imbalances(balances)
            if warnings:
                await notify(
                    "⚠️ <b>Дисбаланс портфеля:</b>\n" + "\n".join(warnings)
                )

        # Выбираем лучшую сделку с учётом портфеля
        best = self._select_best(candidates, balances, TRADER_AMOUNT_USD)
        if best is None:
            return

        spread, buy_bal, sell_bal = best
        await self._execute(spread, TRADER_AMOUNT_USD, buy_bal, sell_bal, notify)

    # ── trade selection ────────────────────────────────────────────────────────

    def _select_best(
        self,
        candidates,
        balances: dict[str, ExchangeBalance],
        trade_usdt: float,
    ):
        """
        Выбирает лучшую сделку с учётом:
        1. Достаточности балансов
        2. Пользы для портфеля
        3. Процента прибыли
        """
        scored = []
        for spread in candidates:
            buy_bal = balances.get(spread.buy_exchange)
            sell_bal = balances.get(spread.sell_exchange)
            if buy_bal is None or sell_bal is None:
                continue

            coin = spread.symbol.split("/")[0]
            coin_needed = trade_usdt / max(spread.book_buy_price, 0.001)

            if self._portfolio:
                ok, reason = self._portfolio.can_execute(
                    spread.buy_exchange, spread.sell_exchange,
                    coin, trade_usdt, coin_needed, buy_bal, sell_bal,
                )
                if not ok:
                    logger.info(f"AutoTrader: пропускаю {spread.symbol} — {reason}")
                    continue

                score = self._portfolio.combined_score(
                    spread.buy_exchange, spread.sell_exchange,
                    coin, spread.net_profit_percent, trade_usdt,
                    buy_bal, sell_bal,
                )
            else:
                # Базовая проверка без portfolio manager
                if buy_bal.usdt < trade_usdt:
                    continue
                if sell_bal.coin(coin) < coin_needed * 0.9:
                    continue
                score = spread.net_profit_percent / 5.0

            scored.append((score, spread, buy_bal, sell_bal))

        if not scored:
            return None

        scored.sort(key=lambda x: x[0], reverse=True)
        _, best_spread, best_buy, best_sell = scored[0]
        return best_spread, best_buy, best_sell

    # ── execution ──────────────────────────────────────────────────────────────

    async def _execute(self, spread, amount_usdt: float, buy_bal, sell_bal, notify) -> None:
        pair_key = f"{spread.symbol}:{spread.buy_exchange}:{spread.sell_exchange}"

        async with self._lock:
            if pair_key in self._active:
                return
            self._active.add(pair_key)

        try:
            coin = spread.symbol.split("/")[0]
            logger.info(
                f"AutoTrader: {spread.symbol} "
                f"{spread.buy_exchange}→{spread.sell_exchange} "
                f"ожид={spread.net_profit_percent:.2f}%"
            )

            buy_order, sell_order = await self.executor.execute_arb(
                symbol=spread.symbol,
                buy_exchange=spread.buy_exchange,
                sell_exchange=spread.sell_exchange,
                usdt_amount=amount_usdt,
            )

            # P&L
            buy_price = buy_order.avg_price if buy_order else 0.0
            sell_price = sell_order.avg_price if sell_order else 0.0
            amount_coin = buy_order.amount_coin if buy_order else 0.0
            buy_cost = buy_order.amount_usdt if buy_order else amount_usdt
            sell_proceeds = sell_order.amount_usdt if sell_order else 0.0

            buy_fee = buy_cost * taker_fee(spread.buy_exchange) / 100
            sell_fee = sell_proceeds * taker_fee(spread.sell_exchange) / 100
            trade_fees = buy_fee + sell_fee
            gross = sell_proceeds - buy_cost
            net = gross - trade_fees

            status = "completed" if (buy_order and sell_order) else "failed"
            error_msg = (
                None if (buy_order and sell_order)
                else ("buy failed" if not buy_order else "sell failed")
            )

            # Обновляем цели портфеля при успешной сделке
            if status == "completed" and self._portfolio and buy_order:
                new_balances = await self.accounts.fetch_all_balances()
                self._portfolio.auto_set_targets_from_balances(new_balances)

            from database.trades_repo import create_trade
            await create_trade(
                symbol=spread.symbol,
                buy_exchange=spread.buy_exchange,
                sell_exchange=spread.sell_exchange,
                amount_usdt=amount_usdt,
                buy_price=buy_price,
                sell_price=sell_price,
                amount_coin=amount_coin,
                gross_profit_usd=gross,
                trade_fees_usd=trade_fees,
                net_profit_usd=net,
                status=status,
                error_msg=error_msg,
            )

            if notify:
                sign = "✅" if net > 0 else ("⚠️" if status == "failed" else "❌")
                await notify(
                    f"{sign} <b>Авто-трейд: {spread.symbol}</b>\n"
                    f"{spread.buy_exchange} → {spread.sell_exchange}\n"
                    f"Размер: <b>${amount_usdt:,.0f}</b> | "
                    f"Монет: {amount_coin:.4f}\n"
                    f"Покупка: {buy_price:.4f}$ → Продажа: {sell_price:.4f}$\n"
                    f"Профит: <b>{net:+.2f} USDT</b>"
                    + (f"\n⚠️ {error_msg}" if error_msg else "")
                )
        finally:
            async with self._lock:
                self._active.discard(pair_key)
