"""Кэш ID администраторов в памяти + sync-проверки для хэндлеров.

Содержит super-admin из ENV + всех с is_admin=True в БД.
"""
from config import ADMIN_TELEGRAM_ID


_admin_ids: set[int] = {ADMIN_TELEGRAM_ID}


def is_admin(user_id: int | None) -> bool:
    if user_id is None:
        return False
    return user_id in _admin_ids


def is_super_admin(user_id: int | None) -> bool:
    return user_id == ADMIN_TELEGRAM_ID


def known_admin_ids() -> set[int]:
    return set(_admin_ids)


async def reload_from_db() -> None:
    """Загрузить дополнительных админов из БД при старте."""
    from database.users_repo import list_admin_user_ids
    extra = await list_admin_user_ids()
    _admin_ids.clear()
    _admin_ids.add(ADMIN_TELEGRAM_ID)
    _admin_ids.update(extra)


def add_to_cache(user_id: int) -> None:
    _admin_ids.add(user_id)


def remove_from_cache(user_id: int) -> bool:
    """False если это super-admin (его нельзя удалить)."""
    if user_id == ADMIN_TELEGRAM_ID:
        return False
    _admin_ids.discard(user_id)
    return True
