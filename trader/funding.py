"""Сканер ставок финансирования (Funding Rate Arbitrage).

Стратегия:
  Купить монету на споте + открыть SHORT в перпах на той же бирже.
  Delta = 0 (не важно куда идёт цена).
  Каждые 8 часов биржа платит лонгам, если funding > 0 (обычно так в бычий рынок).

Доходность:
  0.01%/8ч → ~11% годовых
  0.05%/8ч → ~55% годовых
  0.10%/8ч → ~110% годовых

Риски:
  - Ставка может стать отрицательной (тогда платишь ты)
  - Разница между ценой спота и перпа при закрытии (обычно <0.1%)
  - Биржевой риск (держишь крипту)
"""
import asyncio
from dataclasses import dataclass

import ccxt.async_support as ccxt
from loguru import logger


FUNDING_EXCHANGES = ["bybit", "binance", "okx"]
FUNDING_SYMBOLS = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT"]
FUNDING_MIN_RATE_8H = 0.03    # % за 8 часов — минимум для алерта
FUNDING_GOOD_RATE_8H = 0.05   # % за 8 часов — хорошая возможность


@dataclass
class FundingOpportunity:
    exchange_id: str
    symbol: str
    coin: str
    funding_rate_8h: float      # % за 8 часов
    funding_rate_annual: float  # % годовых (приблизительно)
    next_funding_time: str      # UTC строка
    spot_price: float

    def is_good(self) -> bool:
        return abs(self.funding_rate_8h) >= FUNDING_GOOD_RATE_8H

    def direction(self) -> str:
        """Что делать: long spot + short perp, или short spot + long perp."""
        if self.funding_rate_8h > 0:
            return "long_spot_short_perp"   # лонги платят шортам → шортим перп
        return "short_spot_long_perp"       # шорты платят лонгам → лонгуем перп

    def direction_human(self) -> str:
        if self.funding_rate_8h > 0:
            return "Купить СПОТ + Шорт ПЕРП"
        return "Продать СПОТ + Лонг ПЕРП"

    def format_message(self) -> str:
        sign = "✅" if self.is_good() else "📊"
        arrow = "📈" if self.funding_rate_8h > 0 else "📉"
        return (
            f"{sign} <b>{self.coin}</b> на <b>{self.exchange_id.upper()}</b>\n"
            f"{arrow} Ставка: <b>{self.funding_rate_8h:+.4f}%/8ч</b> "
            f"≈ <b>{self.funding_rate_annual:+.1f}%/год</b>\n"
            f"Действие: {self.direction_human()}\n"
            f"Следующее начисление: {self.next_funding_time} UTC\n"
            f"Цена: ${self.spot_price:,.2f}"
        )


async def _fetch_funding_for_exchange(
    exchange_id: str,
) -> list[FundingOpportunity]:
    cls = getattr(ccxt, exchange_id, None)
    if cls is None:
        return []

    ex = cls({"enableRateLimit": True, "options": {"defaultType": "future"}})
    results = []
    try:
        for symbol in FUNDING_SYMBOLS:
            try:
                info = await ex.fetch_funding_rate(symbol)
                rate = info.get("fundingRate")
                if rate is None:
                    continue
                rate_pct = float(rate) * 100          # в процентах
                annual = rate_pct * 3 * 365           # 3 раза в сутки × 365

                if abs(rate_pct) < FUNDING_MIN_RATE_8H:
                    continue

                # Берём цену с спота
                spot_symbol = symbol.split(":")[0]
                spot_ex = getattr(ccxt, exchange_id)(
                    {"enableRateLimit": True, "options": {"defaultType": "spot"}}
                )
                try:
                    ticker = await spot_ex.fetch_ticker(spot_symbol)
                    spot_price = float(ticker.get("last") or ticker.get("ask") or 0)
                finally:
                    await spot_ex.close()

                next_ts = info.get("fundingDatetime") or info.get("nextFundingDatetime") or "—"

                results.append(FundingOpportunity(
                    exchange_id=exchange_id,
                    symbol=symbol,
                    coin=spot_symbol.split("/")[0],
                    funding_rate_8h=rate_pct,
                    funding_rate_annual=annual,
                    next_funding_time=str(next_ts)[:16],
                    spot_price=spot_price,
                ))
            except Exception as e:
                logger.debug(f"funding [{exchange_id}] {symbol}: {e}")
    finally:
        await ex.close()

    return results


async def scan_funding_rates(
    exchanges: list[str] | None = None,
) -> list[FundingOpportunity]:
    """
    Сканирует ставки финансирования на всех биржах.
    Возвращает список возможностей, отсортированных по доходности.
    """
    targets = exchanges or FUNDING_EXCHANGES
    tasks = [_fetch_funding_for_exchange(ex) for ex in targets]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    opportunities: list[FundingOpportunity] = []
    for res in results:
        if isinstance(res, list):
            opportunities.extend(res)

    opportunities.sort(key=lambda o: abs(o.funding_rate_annual), reverse=True)
    return opportunities


def format_funding_report(opportunities: list[FundingOpportunity]) -> str:
    if not opportunities:
        return (
            "📊 <b>Funding Rate</b>\n\n"
            "Сейчас нет возможностей выше порога "
            f"({FUNDING_MIN_RATE_8H}%/8ч = "
            f"{FUNDING_MIN_RATE_8H * 3 * 365:.0f}%/год).\n\n"
            "Рынок нейтральный — ставки низкие."
        )

    good = [o for o in opportunities if o.is_good()]
    others = [o for o in opportunities if not o.is_good()]

    lines = ["💰 <b>Funding Rate Arbitrage</b>\n"]
    lines.append(
        "<i>Стратегия: открыть дельта-нейтральную позицию и получать "
        "выплаты каждые 8 часов без направленного риска.</i>\n"
    )

    if good:
        lines.append("🔥 <b>Хорошие возможности:</b>")
        for o in good:
            lines.append(o.format_message())
            lines.append("")

    if others:
        lines.append("📊 <b>Умеренные:</b>")
        for o in others:
            lines.append(
                f"• {o.coin} / {o.exchange_id}: "
                f"{o.funding_rate_8h:+.4f}%/8ч "
                f"({o.funding_rate_annual:+.1f}%/год) — {o.direction_human()}"
            )

    lines.append("\n<b>Как войти:</b>")
    lines.append("1. Купить SPOT на сумму N USDT")
    lines.append("2. Открыть SHORT PERP на ту же сумму (1x левередж)")
    lines.append("3. Ждать выплат каждые 8ч")
    lines.append("4. Выйти когда ставка упадёт ниже 0.01%/8ч")

    return "\n".join(lines)
