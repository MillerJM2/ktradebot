"""Тарифы KTradeClub: BASE, STANDART, PRO, PREMIUM."""
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TierFeatures:
    name: str
    price_usd: float
    old_price_usd: float
    duration_days: int
    min_threshold: float
    allowed_exchanges: tuple[str, ...]
    quote_currencies: tuple[str, ...]
    max_signals_per_cycle: int
    bullets: tuple[str, ...]
    is_lifetime: bool = False


ALL_EXCHANGES = ("binance", "bybit", "okx", "kucoin", "gateio", "mexc")


TIERS: dict[str, TierFeatures] = {
    "free": TierFeatures(
        name="Без подписки",
        price_usd=0.0,
        old_price_usd=0.0,
        duration_days=0,
        min_threshold=999.0,
        allowed_exchanges=(),
        quote_currencies=(),
        max_signals_per_cycle=0,
        bullets=(),
    ),
    "base": TierFeatures(
        name="BASE",
        price_usd=490.0,
        old_price_usd=590.0,
        duration_days=90,
        min_threshold=2.0,
        allowed_exchanges=ALL_EXCHANGES,
        quote_currencies=("USDT",),
        max_signals_per_cycle=5,
        bullets=(
            "Доступ на 3 месяца",
            "Торговые пары к USDT",
            "6 CEX бирж",
        ),
    ),
    "standart": TierFeatures(
        name="STANDART",
        price_usd=790.0,
        old_price_usd=990.0,
        duration_days=180,
        min_threshold=1.0,
        allowed_exchanges=ALL_EXCHANGES,
        quote_currencies=("USDT", "BTC"),
        max_signals_per_cycle=10,
        bullets=(
            "Доступ на 6 месяцев",
            "Торговые пары к USDT",
            "Торговые пары к BTC",
            "6 CEX бирж",
        ),
    ),
    "pro": TierFeatures(
        name="PRO",
        price_usd=1190.0,
        old_price_usd=1490.0,
        duration_days=365,
        min_threshold=0.5,
        allowed_exchanges=ALL_EXCHANGES,
        quote_currencies=("USDT", "BTC"),
        max_signals_per_cycle=15,
        bullets=(
            "Доступ на 12 месяцев",
            "Торговые пары к USDT",
            "Торговые пары к BTC",
            "6 CEX бирж",
            "3 онлайн-консультации с менеджером",
        ),
    ),
    "premium": TierFeatures(
        name="PREMIUM",
        price_usd=1590.0,
        old_price_usd=1990.0,
        duration_days=36500,
        min_threshold=0.3,
        allowed_exchanges=ALL_EXCHANGES,
        quote_currencies=("USDT", "BTC"),
        max_signals_per_cycle=30,
        bullets=(
            "Пожизненный доступ",
            "Весь софт от команды KTradeClub",
            "Обучение арбитражу криптовалют",
            "Личный менеджер",
            "Подбор индивидуальных стратегий",
            "Закрытое комьюнити",
        ),
        is_lifetime=True,
    ),
    "admin": TierFeatures(
        name="Admin",
        price_usd=0.0,
        old_price_usd=0.0,
        duration_days=36500,
        min_threshold=0.0,
        allowed_exchanges=ALL_EXCHANGES,
        quote_currencies=("USDT", "BTC"),
        max_signals_per_cycle=100,
        bullets=(),
    ),
}


PAID_TIERS = ("base", "standart", "pro", "premium")


def features(tier: str) -> TierFeatures:
    return TIERS.get(tier, TIERS["free"])


def effective_tier(tier: str, expires_at: datetime | None) -> str:
    if tier in ("free", "admin"):
        return tier
    if expires_at is None:
        return "free"
    if expires_at < datetime.utcnow():
        return "free"
    return tier
