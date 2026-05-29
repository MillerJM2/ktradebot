"""Поиск межбиржевых spot-spot вилок по полученным тикерам."""
from dataclasses import dataclass
from datetime import datetime, timezone

from arbitrage.exchange_info import display_name, taker_fee, trade_url


@dataclass
class Spread:
    symbol: str
    buy_exchange: str
    buy_price: float
    buy_volume_usd: float
    sell_exchange: str
    sell_price: float
    sell_volume_usd: float
    spread_percent: float

    @property
    def total_fees_percent(self) -> float:
        return taker_fee(self.buy_exchange) + taker_fee(self.sell_exchange)

    @property
    def net_spread_percent(self) -> float:
        return self.spread_percent - self.total_fees_percent

    def _profit_for(self, amount_usd: float) -> float:
        return amount_usd * self.net_spread_percent / 100

    @staticmethod
    def _format_volume(vol_usd: float) -> str:
        if vol_usd >= 1_000_000:
            return f"{vol_usd / 1_000_000:,.2f}M USDT"
        if vol_usd >= 1_000:
            return f"{vol_usd / 1_000:,.0f}K USDT"
        return f"{vol_usd:,.0f} USDT"

    @staticmethod
    def _format_price(price: float) -> str:
        if price >= 1:
            return f"{price:,.4f}$"
        return f"{price:.8f}$"

    def format_message(self) -> str:
        buy_url = trade_url(self.buy_exchange, self.symbol)
        sell_url = trade_url(self.sell_exchange, self.symbol)
        buy_name = display_name(self.buy_exchange)
        sell_name = display_name(self.sell_exchange)
        ts = datetime.now(timezone.utc).strftime("%H:%M UTC")

        profit_1000 = self._profit_for(1000)

        return (
            f"<a href=\"{buy_url}\">{buy_name}</a> → "
            f"<a href=\"{sell_url}\">{sell_name}</a> | "
            f"<b>{self.symbol}</b>\n"
            f"\n"
            f"📂 <b>Покупка</b>\n"
            f"\n"
            f"Объём 24ч: {self._format_volume(self.buy_volume_usd)}\n"
            f"Цена: {self._format_price(self.buy_price)}\n"
            f"\n"
            f"📈 <b>Продажа</b>\n"
            f"\n"
            f"Объём 24ч: {self._format_volume(self.sell_volume_usd)}\n"
            f"Цена: {self._format_price(self.sell_price)}\n"
            f"\n"
            f"Профит: <b>{profit_1000:.2f} USDT</b> (на $1000)\n"
            f"Спред: <b>{self.spread_percent:.2f}%</b>\n"
            f"Чистый спред: <b>{self.net_spread_percent:.2f}%</b>\n"
            f"\n"
            f"Комиссии бирж: {self.total_fees_percent:.2f}% "
            f"({taker_fee(self.buy_exchange):.1f}% + {taker_fee(self.sell_exchange):.1f}%)\n"
            f"\n"
            f"⏰ {ts}"
        )


def find_spreads(
    tickers_by_exchange: dict[str, dict[str, dict]],
    min_spread_percent: float,
) -> list[Spread]:
    """Найти все межбиржевые вилки выше порога.

    Логика: для каждой монеты ищем биржу с минимальным ask (там покупаем)
    и биржу с максимальным bid (там продаём). Если разница ≥ порога — это вилка.
    """
    by_symbol: dict[str, list[tuple[str, float, float, float]]] = {}
    for exchange_name, tickers in tickers_by_exchange.items():
        for symbol, prices in tickers.items():
            by_symbol.setdefault(symbol, []).append((
                exchange_name,
                prices["bid"],
                prices["ask"],
                prices.get("quote_volume", 0.0),
            ))

    spreads: list[Spread] = []
    for symbol, entries in by_symbol.items():
        if len(entries) < 2:
            continue

        buy_entry = min(entries, key=lambda e: e[2])
        sell_entry = max(entries, key=lambda e: e[1])
        buy_exchange, _, best_ask, buy_volume = buy_entry
        sell_exchange, best_bid, _, sell_volume = sell_entry

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
                buy_volume_usd=buy_volume,
                sell_exchange=sell_exchange,
                sell_price=best_bid,
                sell_volume_usd=sell_volume,
                spread_percent=spread_percent,
            ))

    spreads.sort(key=lambda s: s.spread_percent, reverse=True)
    return spreads
