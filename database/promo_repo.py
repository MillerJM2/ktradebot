"""CRUD для промокодов."""
from datetime import datetime, timedelta

from sqlalchemy import delete, select, update

from database.models import PromoCode, PromoUsage, User
from database.session import async_session_factory


async def create_promo(
    code: str,
    type_: str,
    value: float,
    tier: str | None = None,
    max_uses: int = 0,
    expires_days: int | None = None,
) -> PromoCode:
    expires_at = None
    if expires_days and expires_days > 0:
        expires_at = datetime.utcnow() + timedelta(days=expires_days)
    async with async_session_factory() as session:
        promo = PromoCode(
            code=code.upper(),
            type=type_,
            value=value,
            tier=tier,
            max_uses=max_uses,
            uses_count=0,
            expires_at=expires_at,
        )
        session.add(promo)
        await session.commit()
        await session.refresh(promo)
        return promo


async def get_promo(code: str) -> PromoCode | None:
    async with async_session_factory() as session:
        return await session.get(PromoCode, code.upper())


async def delete_promo(code: str) -> bool:
    async with async_session_factory() as session:
        promo = await session.get(PromoCode, code.upper())
        if not promo:
            return False
        await session.delete(promo)
        await session.commit()
        return True


async def list_promos() -> list[PromoCode]:
    async with async_session_factory() as session:
        result = await session.execute(select(PromoCode).order_by(PromoCode.created_at.desc()))
        return list(result.scalars().all())


async def has_user_used(code: str, user_id: int) -> bool:
    async with async_session_factory() as session:
        result = await session.execute(
            select(PromoUsage).where(
                PromoUsage.code == code.upper(),
                PromoUsage.user_id == user_id,
            )
        )
        return result.first() is not None


async def record_usage(
    code: str, user_id: int, tier_applied: str | None, discount_value: float
) -> None:
    async with async_session_factory() as session:
        session.add(PromoUsage(
            code=code.upper(),
            user_id=user_id,
            tier_applied=tier_applied,
            discount_value=discount_value,
        ))
        await session.execute(
            update(PromoCode)
            .where(PromoCode.code == code.upper())
            .values(uses_count=PromoCode.uses_count + 1)
        )
        await session.commit()


async def set_user_pending_promo(user_id: int, code: str | None) -> None:
    async with async_session_factory() as session:
        await session.execute(
            update(User)
            .where(User.telegram_id == user_id)
            .values(pending_promo_code=code)
        )
        await session.commit()


def validate(promo: PromoCode | None) -> str | None:
    """None — промо валиден, иначе текст ошибки."""
    if promo is None:
        return "Промокод не найден."
    if promo.expires_at and promo.expires_at < datetime.utcnow():
        return "Промокод истёк."
    if promo.max_uses and promo.uses_count >= promo.max_uses:
        return "Лимит использований промокода исчерпан."
    return None
