"""CRUD-операции для пользователей."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from config import ADMIN_TELEGRAM_ID, DEFAULT_SPREAD_THRESHOLD
from database.models import User
from database.session import async_session_factory


async def get_or_create_user(
    telegram_id: int,
    username: str | None = None,
) -> User:
    async with async_session_factory() as session:
        user = await session.get(User, telegram_id)
        if user is None:
            is_admin = telegram_id == ADMIN_TELEGRAM_ID
            now = datetime.now(timezone.utc)
            user = User(
                telegram_id=telegram_id,
                username=username,
                tier="admin" if is_admin else "trial",
                threshold=DEFAULT_SPREAD_THRESHOLD,
                paused=False,
                trial_used=not is_admin,
                # Пропускаем 7-д и 3-д напоминания — у триала только 3 дня
                reminder_milestone=3 if not is_admin else 999,
            )
            if not is_admin:
                user.subscription_expires_at = now + timedelta(days=3)
            session.add(user)
            await session.commit()
            await session.refresh(user)
        else:
            user.last_active_at = datetime.now(timezone.utc)
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


async def grant_subscription(
    telegram_id: int, tier: str, days: int
) -> User | None:
    async with async_session_factory() as session:
        user = await session.get(User, telegram_id)
        if user is None:
            return None
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        expires = user.subscription_expires_at
        base = expires if (expires and expires.replace(tzinfo=None) > now) else now
        user.tier = tier
        user.subscription_expires_at = base + timedelta(days=days)
        user.reminder_milestone = 999
        await session.commit()
        await session.refresh(user)
        return user


async def set_reminder_milestone(telegram_id: int, milestone: int) -> None:
    async with async_session_factory() as session:
        await session.execute(
            update(User)
            .where(User.telegram_id == telegram_id)
            .values(reminder_milestone=milestone)
        )
        await session.commit()


async def get_users_with_active_subscription() -> list[User]:
    async with async_session_factory() as session:
        result = await session.execute(
            select(User).where(
                User.tier.in_(["trial", "base", "standart", "pro", "premium"]),
                User.subscription_expires_at.is_not(None),
            )
        )
        return list(result.scalars().all())


async def set_referrer(telegram_id: int, referrer_id: int) -> None:
    if referrer_id == telegram_id:
        return
    async with async_session_factory() as session:
        user = await session.get(User, telegram_id)
        if user is None or user.referrer_id is not None:
            return
        user.referrer_id = referrer_id
        await session.commit()


async def add_referral_balance(referrer_id: int, amount_usd: float) -> None:
    async with async_session_factory() as session:
        user = await session.get(User, referrer_id)
        if user is None:
            return
        user.referral_balance_usd = (user.referral_balance_usd or 0.0) + amount_usd
        user.total_referral_earned_usd = (user.total_referral_earned_usd or 0.0) + amount_usd
        await session.commit()


async def withdraw_referral_balance(telegram_id: int) -> float:
    """Атомарно обнуляет баланс и возвращает старое значение."""
    async with async_session_factory() as session:
        user = await session.get(User, telegram_id)
        if user is None:
            return 0.0
        amount = user.referral_balance_usd or 0.0
        user.referral_balance_usd = 0.0
        await session.commit()
        return amount


async def restore_referral_balance(telegram_id: int, amount_usd: float) -> None:
    """Откатываем списание, если CryptoBot transfer не прошёл."""
    async with async_session_factory() as session:
        user = await session.get(User, telegram_id)
        if user is None:
            return
        user.referral_balance_usd = (user.referral_balance_usd or 0.0) + amount_usd
        await session.commit()


async def count_referrals(referrer_id: int) -> int:
    async with async_session_factory() as session:
        result = await session.execute(
            select(User).where(User.referrer_id == referrer_id)
        )
        return len(list(result.scalars().all()))


async def revoke_subscription(telegram_id: int) -> None:
    async with async_session_factory() as session:
        await session.execute(
            update(User)
            .where(User.telegram_id == telegram_id)
            .values(tier="free", subscription_expires_at=None)
        )
        await session.commit()


async def get_user(telegram_id: int) -> User | None:
    async with async_session_factory() as session:
        return await session.get(User, telegram_id)


async def find_user_by_username(username: str) -> User | None:
    normalized = username.lstrip("@").lower()
    async with async_session_factory() as session:
        result = await session.execute(
            select(User).where(User.username.is_not(None))
        )
        for u in result.scalars().all():
            if u.username and u.username.lower() == normalized:
                return u
        return None


async def get_active_users() -> list[User]:
    async with async_session_factory() as session:
        result = await session.execute(
            select(User).where(User.paused.is_(False))
        )
        return list(result.scalars().all())


async def list_users() -> list[User]:
    async with async_session_factory() as session:
        result = await session.execute(select(User))
        return list(result.scalars().all())


async def count_users() -> int:
    async with async_session_factory() as session:
        result = await session.execute(select(User))
        return len(list(result.scalars().all()))
