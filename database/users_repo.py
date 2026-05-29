"""CRUD-операции для пользователей."""
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from config import ADMIN_TELEGRAM_ID, DEFAULT_SPREAD_THRESHOLD
from database.models import User
from database.session import async_session_factory


async def get_or_create_user(
    telegram_id: int,
    username: str | None = None,
) -> User:
    """Найти юзера или создать нового. Админ автоматически получает тариф 'admin'."""
    async with async_session_factory() as session:
        user = await session.get(User, telegram_id)
        if user is None:
            user = User(
                telegram_id=telegram_id,
                username=username,
                tier="admin" if telegram_id == ADMIN_TELEGRAM_ID else "free",
                threshold=DEFAULT_SPREAD_THRESHOLD,
                paused=False,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
        else:
            user.last_active_at = datetime.utcnow()
            if username and user.username != username:
                user.username = username
            await session.commit()
            await session.refresh(user)
        return user


async def set_threshold(telegram_id: int, threshold: float) -> None:
    async with async_session_factory() as session:
        await session.execute(
            update(User)
            .where(User.telegram_id == telegram_id)
            .values(threshold=threshold)
        )
        await session.commit()


async def set_paused(telegram_id: int, paused: bool) -> None:
    async with async_session_factory() as session:
        await session.execute(
            update(User)
            .where(User.telegram_id == telegram_id)
            .values(paused=paused)
        )
        await session.commit()


async def get_user(telegram_id: int) -> User | None:
    async with async_session_factory() as session:
        return await session.get(User, telegram_id)


async def get_active_users() -> list[User]:
    """Все юзеры, у которых не на паузе."""
    async with async_session_factory() as session:
        result = await session.execute(
            select(User).where(User.paused.is_(False))
        )
        return list(result.scalars().all())


async def count_users() -> int:
    async with async_session_factory() as session:
        result = await session.execute(select(User))
        return len(list(result.scalars().all()))
