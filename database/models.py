"""ORM-модели SQLAlchemy."""
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Float, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String, nullable=True)
    tier: Mapped[str] = mapped_column(String, default="free")
    threshold: Mapped[float] = mapped_column(Float, default=2.0)
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    subscription_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_active_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    referrer_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    referral_balance_usd: Mapped[float] = mapped_column(Float, default=0.0)
    total_referral_earned_usd: Mapped[float] = mapped_column(Float, default=0.0)
    reminder_milestone: Mapped[int] = mapped_column(Integer, default=999)
    pending_promo_code: Mapped[str | None] = mapped_column(String, nullable=True)


class Invoice(Base):
    __tablename__ = "invoices"

    invoice_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    tier: Mapped[str] = mapped_column(String)
    days: Mapped[int] = mapped_column(Integer, default=30)
    amount_usd: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String, default="active")  # active|paid|expired|delivered
    pay_url: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class BotSetting(Base):
    __tablename__ = "bot_settings"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String)


class PromoCode(Base):
    __tablename__ = "promo_codes"

    code: Mapped[str] = mapped_column(String, primary_key=True)
    type: Mapped[str] = mapped_column(String)  # "discount" | "trial"
    value: Mapped[float] = mapped_column(Float)  # percent for discount, days for trial
    tier: Mapped[str | None] = mapped_column(String, nullable=True)  # for trial only
    max_uses: Mapped[int] = mapped_column(Integer, default=0)  # 0 = unlimited
    uses_count: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PromoUsage(Base):
    __tablename__ = "promo_usages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    used_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    tier_applied: Mapped[str | None] = mapped_column(String, nullable=True)
    discount_value: Mapped[float] = mapped_column(Float, default=0.0)


class SignalLog(Base):
    __tablename__ = "signals_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    symbol: Mapped[str] = mapped_column(String, index=True)
    buy_exchange: Mapped[str] = mapped_column(String, index=True)
    sell_exchange: Mapped[str] = mapped_column(String, index=True)
    net_profit_percent: Mapped[float] = mapped_column(Float)
    raw_spread_percent: Mapped[float] = mapped_column(Float)
    buy_volume_usd: Mapped[float] = mapped_column(Float, default=0.0)
    sell_volume_usd: Mapped[float] = mapped_column(Float, default=0.0)
    network: Mapped[str] = mapped_column(String, default="")
    withdraw_fee_usd: Mapped[float] = mapped_column(Float, default=0.0)
    target_amount_usd: Mapped[float] = mapped_column(Float, default=1000.0)
