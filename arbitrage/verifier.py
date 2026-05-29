"""Применение фильтров 1-4 к сырому кандидату-спреду.

Фильтр 1 — вывод включён на бирже покупки.
Фильтр 2 — депозит включён на бирже продажи.
Фильтр 3 — есть общая рабочая сеть для перевода.
Фильтр 4 — реальный спред по стакану выше порога после всех комиссий.
"""
from dataclasses import dataclass
from datetime import datetime, timezone

from arbitrage.exchange_info import display_name, taker_fee, trade_url
from config import (
    MAX_PROFIT_PERCENT,
    MIN_PROFIT_PERCENT,
    TARGET_AMOUNT_USD,
)
from exchanges.currencies_cache import cache as currencies_cache
from exchanges.order_book import real_execution_prices


@dataclass
class VerifiedSpread:
    symbol: str
    buy_exchange: str
    sell_exchange: str
    book_buy_price: float
    book_sell_price: float
    buy_volume_usd: float
    sell_volume_usd: float
    raw_spread_percent: float
    net_profit_percent: float
    profit_usd: float
    network: str
    withdraw_fee_coin: float
    withdraw_fee_usd: float
    trade_fees_percent: float
    target_amount_usd: float

    @staticmethod
    def _fmt_vol(vol_usd: float) -> str:
        if vol_usd >= 1_000_000:
            return f"{vol_usd / 1_000_000:,.2f}M USDT"
        if vol_usd >= 1_000:
            return f"{vol_usd / 1_000:,.0f}K USDT"
        return f"{vol_usd:,.0f} USDT"

    @staticmethod
    def _fmt_price(price: float) -> str:
        if price >= 1:
            return f"{price:,.4f}$"
        return f"{price:.8f}$"

    def format_message(self) -> str:
        buy_url = trade_url(self.buy_exchange, self.symbol)
        sell_url = trade_url(self.sell_exchange, self.symbol)
        buy_name = display_name(self.buy_exchange)
        sell_name = display_name(self.sell_exchange)
        ts = datetime.now(timezone.utc).strftime("%H:%M UTC")

        return (
            f"<a href=\"{buy_url}\">{buy_name}</a> → "
            f"<a href=\"{sell_url}\">{sell_name}</a> | "
            f"<b>{self.symbol}</b>\n"
            f"\n"
            f"📂 <b>Покупка</b>\n"
            f"Объём 24ч: {self._fmt_vol(self.buy_volume_usd)}\n"
            f"Цена (стакан): {self._fmt_price(self.book_buy_price)}\n"
            f"\n"
            f"📈 <b>Продажа</b>\n"
            f"Объём 24ч: {self._fmt_vol(self.sell_volume_usd)}\n"
            f"Цена (стакан): {self._fmt_price(self.book_sell_price)}\n"
            f"\n"
            f"💰 <b>Профит: {self.profit_usd:,.2f} USDT</b> (на ${self.target_amount_usd:,.0f})\n"
            f"Чистый спред: <b>{self.net_profit_percent:.2f}%</b>\n"
            f"Сырой спред: {self.raw_spread_percent:.2f}%\n"
            f"\n"
            f"✉️ <b>Вывод</b>\n"
            f"Сеть: <code>{self.network}</code>\n"
            f"Комиссия вывода: {self.withdraw_fee_coin:g} "
            f"({self.withdraw_fee_usd:.2f}$)\n"
            f"\n"
            f"Торговые комиссии: {self.trade_fees_percent:.2f}%\n"
            f"⏰ {ts}"
        )


async def verify_spread(
    symbol: str,
    buy_exchange: str,
    buy_volume_usd: float,
    sell_exchange: str,
    sell_volume_usd: float,
) -> VerifiedSpread | None:
    """Полный проход через все 4 фильтра. None если хотя бы один не пройден."""
    coin = symbol.split("/", 1)[0]

    if not currencies_cache.can_withdraw(buy_exchange, coin):
        return None
    if not currencies_cache.can_deposit(sell_exchange, coin):
        return None

    network_info = currencies_cache.find_common_network(buy_exchange, sell_exchange, coin)
    if network_info is None:
        return None
    network_name, withdraw_fee_coin = network_info

    prices = await real_execution_prices(
        symbol, buy_exchange, sell_exchange, TARGET_AMOUNT_USD
    )
    if prices is None:
        return None
    avg_buy, avg_sell = prices

    raw_spread = (avg_sell - avg_buy) / avg_buy * 100
    trade_fees = taker_fee(buy_exchange) + taker_fee(sell_exchange)
    withdraw_fee_usd = withdraw_fee_coin * avg_buy
    withdraw_fee_pct = withdraw_fee_usd / TARGET_AMOUNT_USD * 100

    net_profit_pct = raw_spread - trade_fees - withdraw_fee_pct
    if net_profit_pct < MIN_PROFIT_PERCENT:
        return None
    if net_profit_pct > MAX_PROFIT_PERCENT:
        return None

    profit_usd = TARGET_AMOUNT_USD * net_profit_pct / 100

    return VerifiedSpread(
        symbol=symbol,
        buy_exchange=buy_exchange,
        sell_exchange=sell_exchange,
        book_buy_price=avg_buy,
        book_sell_price=avg_sell,
        buy_volume_usd=buy_volume_usd,
        sell_volume_usd=sell_volume_usd,
        raw_spread_percent=raw_spread,
        net_profit_percent=net_profit_pct,
        profit_usd=profit_usd,
        network=network_name,
        withdraw_fee_coin=withdraw_fee_coin,
        withdraw_fee_usd=withdraw_fee_usd,
        trade_fees_percent=trade_fees,
        target_amount_usd=TARGET_AMOUNT_USD,
    )
