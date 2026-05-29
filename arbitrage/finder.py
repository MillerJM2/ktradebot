"""Поиск межбиржевых spot-spot вилок по полученным тикерам."""
from dataclasses import dataclass


@dataclass
class Spread:
    symbol: str
    buy_exchange: str
    buy_price: float
    sell_exchange: str
    sell_price: float
    spread_percent: float

    def format_message(self) -> str:
        return (
            f"💰 Вилка по <b>{self.symbol}</b>\n"
            f"Купить на <b>{self.buy_exchange}</b>: {self.buy_price:.8f}\n"
            f"Продать на <b>{self.sell_exchange}</b>: {self.sell_price:.8f}\n"
            f"Спред: <b>{self.spread_percent:.2f}%</b>"
        )


def find_spreads(
    tickers_by_exchange: dict[str, dict[str, dict]],
    min_spread_percent: float,
) -> list[Spread]:
    """Найти все межбиржевые вилки выше порога.

    Логика: для каждой монеты ищем биржу с минимальным ask (там покупаем)
    и биржу с максимальным bid (там продаём). Если разница ≥ порога — это вилка.
    """
    by_symbol: dict[str, list[tuple[str, float, float]]] = {}
    for exchange_name, tickers in tickers_by_exchange.items():
        for symbol, prices in tickers.items():
            by_symbol.setdefault(symbol, []).append(
                (exchange_name, prices["bid"], prices["ask"])
            )

    spreads: list[Spread] = []
    for symbol, entries in by_symbol.items():
        if len(entries) < 2:
            continue

        buy_exchange, _, best_ask = min(entries, key=lambda e: e[2])
        sell_exchange, best_bid, _ = max(entries, key=lambda e: e[1])

        if buy_exchange == sell_exchange:
            continue
        if best_ask <= 0:
            continue

        spread_percent = (best_bid - best_ask) / best_ask * 100

        if spread_percent >= min_spread_percent:
            spreads.append(Spread(
                symbol=symbol,
                buy_exchange=buy_exchange,
                buy_price=best_ask,
                sell_exchange=sell_exchange,
                sell_price=best_bid,
                spread_percent=spread_percent,
            ))

    spreads.sort(key=lambda s: s.spread_percent, reverse=True)
    return spreads
