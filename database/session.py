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


async def _migrate_users() -> None:
    """Добавляет недостающие колонки в таблицу users (для SQLite)."""
    needed = {
        "subscription_expires_at": "DATETIME",
    }
    async with engine.begin() as conn:
        cols = await conn.execute(text("PRAGMA table_info(users)"))
        existing = {row[1] for row in cols.fetchall()}
        for col_name, col_type in needed.items():
            if col_name not in existing:
                logger.info(f"Migration: adding users.{col_name}")
                await conn.execute(
                    text(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
                )


async def init_db() -> None:
    """Создаёт таблицы и добавляет недостающие колонки."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _migrate_users()
