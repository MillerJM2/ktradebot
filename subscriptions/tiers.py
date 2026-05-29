"""Тарифы и их ограничения.

Free       — 2 биржи (Binance, Bybit), порог от 5%, до 1 сигнала за цикл.
Basic ($15)— 4 биржи, порог от 2%, до 5 сигналов за цикл.
Pro ($40)  — все 6 бирж, порог от 0.5%, до 10 сигналов за цикл.
VIP ($100) — Pro + автоторговля (этап 5), до 20 сигналов за цикл.
Admin      — всё без ограничений.
"""
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TierFeatures:
    name: str
    price_usd: float
    min_threshold: float
    allowed_exchanges: tuple[str, ...]
    max_signals_per_cycle: int


TIERS: dict[str, TierFeatures] = {
    "free": TierFeatures(
        name="Free",
        price_usd=0.0,
        min_threshold=5.0,
        allowed_exchanges=("binance", "bybit"),
        max_signals_per_cycle=1,
    ),
    "basic": TierFeatures(
        name="Basic",
        price_usd=15.0,
        min_threshold=2.0,
        allowed_exchanges=("binance", "bybit", "okx", "kucoin"),
        max_signals_per_cycle=5,
    ),
    "pro": TierFeatures(
        name="Pro",
        price_usd=40.0,
        min_threshold=0.5,
        allowed_exchanges=("binance", "bybit", "okx", "kucoin", "gateio", "mexc"),
        max_signals_per_cycle=10,
    ),
    "vip": TierFeatures(
        name="VIP",
        price_usd=100.0,
        min_threshold=0.3,
        allowed_exchanges=("binance", "bybit", "okx", "kucoin", "gateio", "mexc"),
        max_signals_per_cycle=20,
    ),
    "admin": TierFeatures(
        name="Admin",
        price_usd=0.0,
        min_threshold=0.0,
        allowed_exchanges=("binance", "bybit", "okx", "kucoin", "gateio", "mexc"),
        max_signals_per_cycle=100,
    ),
}


def features(tier: str) -> TierFeatures:
    return TIERS.get(tier, TIERS["free"])


def effective_tier(tier: str, expires_at: datetime | None) -> str:
    """Тариф с учётом срока действия. Если подписка истекла — возвращает 'free'."""
    if tier in ("free", "admin"):
        return tier
    if expires_at is None:
        return "free"
    if expires_at < datetime.utcnow():
        return "free"
    return tier
