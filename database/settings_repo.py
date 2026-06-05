"""Простой key-value стор для динамических настроек админа (канал и т.п.)."""
from sqlalchemy import select

from database.models import BotSetting
from database.session import async_session_factory


async def get_setting(key: str, default: str | None = None) -> str | None:
    async with async_session_factory() as session:
        result = await session.execute(select(BotSetting).where(BotSetting.key == key))
        row = result.scalar_one_or_none()
        return row.value if row else default


async def set_setting(key: str, value: str) -> None:
    async with async_session_factory() as session:
        existing = await session.get(BotSetting, key)
        if existing:
            existing.value = value
        else:
            session.add(BotSetting(key=key, value=value))
        await session.commit()


async def get_bool(key: str, default: bool = False) -> bool:
    v = await get_setting(key)
    if v is None:
        return default
    return v.lower() in ("1", "true", "on", "yes")


async def get_int(key: str, default: int = 0) -> int:
    v = await get_setting(key)
    try:
        return int(v) if v else default
    except ValueError:
        return default


async def get_float(key: str, default: float = 0.0) -> float:
    v = await get_setting(key)
    try:
        return float(v) if v else default
    except ValueError:
        return default
