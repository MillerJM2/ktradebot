"""ORM-модели SQLAlchemy."""
from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, DateTime, Float, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _now() -> datetime:
    return datetime.now(timezone.utc)


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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    last_active_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    referrer_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    referral_balance_usd: Mapped[float] = mapped_column(Float, default=0.0)
    total_referral_earned_usd: Mapped[float] = mapped_column(Float, default=0.0)
    reminder_milestone: Mapped[int] = mapped_column(Integer, default=999)
    trial_used: Mapped[bool] = mapped_column(Boolean, default=False)


class Invoice(Base):
    __tablename__ = "invoices"

    invoice_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    tier: Mapped[str] = mapped_column(String)
    days: Mapped[int] = mapped_column(Integer, default=30)
    amount_usd: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String, default="active")  # active|paid|expired|delivered
    pay_url: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String)
    buy_exchange: Mapped[str] = mapped_column(String)
    sell_exchange: Mapped[str] = mapped_column(String)
    amount_usdt: Mapped[float] = mapped_column(Float)
    buy_price: Mapped[float] = mapped_column(Float, default=0.0)
    sell_price: Mapped[float] = mapped_column(Float, default=0.0)
    amount_coin: Mapped[float] = mapped_column(Float, default=0.0)
    gross_profit_usd: Mapped[float] = mapped_column(Float, default=0.0)
    trade_fees_usd: Mapped[float] = mapped_column(Float, default=0.0)
    net_profit_usd: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String, default="completed")  # completed|failed
    error_msg: Mapped[str | None] = mapped_column(String, nullable=True)
    executed_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
