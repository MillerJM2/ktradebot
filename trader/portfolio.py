"""Управление портфелем: отслеживание инвентаря и предпочтения сделок."""
from dataclasses import dataclass, field
from typing import Optional

from .accounts import ExchangeBalance


@dataclass
class InventoryStatus:
    exchange_id: str
    coin: str
    actual: float
    target: float

    @property
    def surplus(self) -> float:
        return self.actual - self.target

    @property
    def surplus_pct(self) -> float:
        if self.target <= 0:
            return 0.0
        return self.surplus / self.target * 100

    @property
    def is_critically_low(self) -> bool:
        return self.actual < self.target * 0.2

    @property
    def is_abundant(self) -> bool:
        return self.actual > self.target * 1.8


class PortfolioManager:
    """
    Отслеживает целевые и фактические балансы.
    Помогает выбрать сделки которые улучшают баланс портфеля.
    """

    def __init__(
        self,
        exchanges: list[str],
        target_usdt_per_exchange: float,
        min_usdt_reserve: float = 50.0,
    ):
        self.exchanges = exchanges
        self.target_usdt = target_usdt_per_exchange
        self.min_usdt_reserve = min_usdt_reserve
        # {exchange_id: {coin: target_amount}}
        self._coin_targets: dict[str, dict[str, float]] = {ex: {} for ex in exchanges}

    def set_coin_target(self, coin: str, total_amount: float) -> None:
        """Установить суммарный целевой объём монеты — равномерно по биржам."""
        per_exchange = total_amount / max(len(self.exchanges), 1)
        for ex in self.exchanges:
            self._coin_targets.setdefault(ex, {})[coin] = per_exchange

    def auto_set_targets_from_balances(
        self, balances: dict[str, ExchangeBalance]
    ) -> None:
        """Установить цели на основе текущих фактических балансов (по умолчанию)."""
        # Считаем итог по каждой монете
        coin_totals: dict[str, float] = {}
        for bal in balances.values():
            for coin, amount in bal.coins.items():
                coin_totals[coin] = coin_totals.get(coin, 0.0) + amount

        for coin, total in coin_totals.items():
            self.set_coin_target(coin, total)

    # ── Проверка возможности сделки ────────────────────────────────────────────

    def can_execute(
        self,
        buy_exchange: str,
        sell_exchange: str,
        coin: str,
        trade_usdt: float,
        coin_amount: float,
        buy_bal: ExchangeBalance,
        sell_bal: ExchangeBalance,
    ) -> tuple[bool, str]:
        """Возвращает (можно_исполнить, причина_отказа)."""
        usdt_after = buy_bal.usdt - trade_usdt
        if usdt_after < self.min_usdt_reserve:
            return (
                False,
                f"USDT на {buy_exchange} упадёт до {usdt_after:.0f} "
                f"(резерв {self.min_usdt_reserve:.0f})",
            )

        coin_after = sell_bal.coin(coin) - coin_amount
        if coin_after < 0:
            return False, f"{coin} на {sell_exchange} недостаточно"

        return True, ""

    # ── Оценка полезности сделки для портфеля ─────────────────────────────────

    def balance_score(
        self,
        buy_exchange: str,
        sell_exchange: str,
        coin: str,
        trade_usdt: float,
        buy_bal: ExchangeBalance,
        sell_bal: ExchangeBalance,
    ) -> float:
        """
        Возвращает от -1.0 до +1.0.
        +1 = сделка идеально восстанавливает баланс (используем избыток USDT и монет)
        0  = нейтрально
        -1 = сделка усугубляет дисбаланс
        """
        # Оцениваем избыток USDT на бирже покупки
        usdt_excess_ratio = (buy_bal.usdt - self.target_usdt) / max(self.target_usdt, 1)

        # Оцениваем избыток монеты на бирже продажи
        target_coin = self._coin_targets.get(sell_exchange, {}).get(coin, 0)
        if target_coin > 0:
            coin_excess_ratio = (sell_bal.coin(coin) - target_coin) / target_coin
        else:
            coin_excess_ratio = 0.0

        # Чем больше избыток — тем лучше использовать их в сделке
        raw = (usdt_excess_ratio + coin_excess_ratio) / 2
        return max(-1.0, min(1.0, raw))

    def combined_score(
        self,
        buy_exchange: str,
        sell_exchange: str,
        coin: str,
        net_profit_pct: float,
        trade_usdt: float,
        buy_bal: ExchangeBalance,
        sell_bal: ExchangeBalance,
        profit_weight: float = 0.7,
    ) -> float:
        """
        Итоговый приоритет сделки: профит + балансовая польза.
        profit_weight: 0.7 = 70% profit, 30% balance
        """
        profit_norm = min(net_profit_pct / 5.0, 1.0)  # нормируем к [0,1] относительно 5%
        bal = self.balance_score(
            buy_exchange, sell_exchange, coin, trade_usdt, buy_bal, sell_bal
        )
        return profit_weight * profit_norm + (1 - profit_weight) * (bal + 1) / 2

    # ── Детектор дисбаланса ────────────────────────────────────────────────────

    def check_imbalances(
        self, balances: dict[str, ExchangeBalance]
    ) -> list[str]:
        """
        Возвращает список предупреждений о критических дисбалансах.
        Используется для уведомлений и команды /balances.
        """
        warnings: list[str] = []

        for ex_id, bal in balances.items():
            # USDT дисбаланс
            if bal.usdt < self.min_usdt_reserve:
                warnings.append(
                    f"⚠️ {ex_id}: USDT критически мало ({bal.usdt:.0f}), "
                    f"нужен перевод USDT"
                )
            elif bal.usdt < self.target_usdt * 0.3:
                warnings.append(
                    f"⚠️ {ex_id}: USDT ниже 30% цели ({bal.usdt:.0f} / {self.target_usdt:.0f})"
                )

            # Монеты дисбаланс
            for coin, target in self._coin_targets.get(ex_id, {}).items():
                if target <= 0:
                    continue
                actual = bal.coin(coin)
                ratio = actual / target
                if ratio < 0.2:
                    warnings.append(
                        f"⚠️ {ex_id}: {coin} критически мало "
                        f"({actual:.4f} / цель {target:.4f}) — нужен перевод"
                    )

        return warnings

    def rebalance_suggestions(
        self, balances: dict[str, ExchangeBalance]
    ) -> list[str]:
        """
        Конкретные инструкции что куда перевести для восстановления баланса.
        """
        suggestions: list[str] = []
        seen_coins = set()
        for bal in balances.values():
            seen_coins.update(bal.coins.keys())

        for coin in seen_coins:
            # Сортируем биржи по избытку монеты
            positions = []
            for ex_id, bal in balances.items():
                target = self._coin_targets.get(ex_id, {}).get(coin, 0)
                actual = bal.coin(coin)
                positions.append((ex_id, actual, target))

            positions.sort(key=lambda x: x[1] - x[2], reverse=True)  # surplus desc
            donor = positions[0]    # больше всего монет
            needy = positions[-1]   # меньше всего

            donor_surplus = donor[1] - donor[2]
            needy_deficit = needy[2] - needy[1]

            if donor_surplus > needy[2] * 0.5 and needy_deficit > needy[2] * 0.3:
                transfer_amount = min(donor_surplus * 0.5, needy_deficit)
                suggestions.append(
                    f"🔄 Перевести {transfer_amount:.4f} {coin}: "
                    f"{donor[0]} → {needy[0]}"
                )

        return suggestions
