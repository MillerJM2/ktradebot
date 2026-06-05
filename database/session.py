"""Создание движка БД, фабрики сессий и лёгкие in-place миграции для SQLite."""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from loguru import logger

from config import DATABASE_URL
from database.models import Base


engine = create_async_engine(DATABASE_URL, echo=False)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def _add_missing_columns(table: str, columns: dict[str, str]) -> None:
    async with engine.begin() as conn:
        cols = await conn.execute(text(f"PRAGMA table_info({table})"))
        existing = {row[1] for row in cols.fetchall()}
        for col_name, col_type in columns.items():
            if col_name not in existing:
                logger.info(f"Migration: adding {table}.{col_name}")
                await conn.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")
                )


async def _migrate_content_templates() -> None:
    await _add_missing_columns("content_templates", {
        "category": "TEXT",
    })


async def _migrate_users() -> None:
    await _add_missing_columns("users", {
        "subscription_expires_at": "DATETIME",
        "referrer_id": "INTEGER",
        "referral_balance_usd": "FLOAT DEFAULT 0",
        "total_referral_earned_usd": "FLOAT DEFAULT 0",
        "reminder_milestone": "INTEGER DEFAULT 999",
        "pending_promo_code": "TEXT",
        "is_admin": "INTEGER DEFAULT 0",
    })


async def init_db() -> None:
    """Создаёт таблицы и добавляет недостающие колонки."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _migrate_users()
    await _migrate_content_templates()
