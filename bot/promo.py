"""Промокоды: команды админа + ввод/применение пользователями."""
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from loguru import logger

from bot.admins import is_admin as _is_admin_uid
from database.promo_repo import (
    create_promo,
    delete_promo,
    get_promo,
    has_user_used,
    list_promos,
    record_usage,
    set_user_pending_promo,
    validate,
)
from database.users_repo import get_or_create_user, grant_subscription
from subscriptions.tiers import PAID_TIERS, features


router = Router()


_pending_input: dict[int, bool] = {}


def _is_admin(message: Message) -> bool:
    return message.from_user is not None and _is_admin_uid(message.from_user.id)


def _waiting_promo(message: Message) -> bool:
    return _pending_input.get(message.from_user.id, False) if message.from_user else False


@router.callback_query(F.data == "promo_enter")
async def cb_enter_promo(callback) -> None:
    user_id = callback.from_user.id
    _pending_input[user_id] = True
    await callback.answer()
    await callback.message.answer(
        "🎟️ Введи промокод одним сообщением (например, <code>WELCOME20</code>).\n"
        "Для отмены — /cancel"
    )


@router.message(Command("cancel"))
async def cmd_cancel_promo(message: Message) -> None:
    if _pending_input.pop(message.from_user.id, False):
        await message.answer("❌ Ввод промокода отменён.")


@router.message(_waiting_promo)
async def handle_promo_input(message: Message) -> None:
    user_id = message.from_user.id
    _pending_input.pop(user_id, None)
    code = (message.text or "").strip().upper()
    if not code:
        await message.answer("❌ Пустое сообщение. Попробуй ещё раз.")
        return

    promo = await get_promo(code)
    err = validate(promo)
    if err:
        await message.answer(f"❌ {err}")
        return
    if await has_user_used(code, user_id):
        await message.answer("❌ Ты уже использовал этот промокод.")
        return

    await get_or_create_user(user_id, message.from_user.username)

    if promo.type == "trial":
        tier = promo.tier or "base"
        days = int(promo.value)
        user = await grant_subscription(user_id, tier, days)
        await record_usage(code, user_id, tier, 0.0)
        if user:
            expires = user.subscription_expires_at.strftime("%Y-%m-%d %H:%M UTC") if user.subscription_expires_at else "—"
            await message.answer(
                f"🎉 <b>Промокод применён!</b>\n\n"
                f"Тариф: <b>{features(tier).name}</b>\n"
                f"Активен до: {expires}\n\n"
                f"Сигналы начнут приходить в течение пары минут."
            )
        else:
            await message.answer("❌ Не удалось активировать. Попробуй позже.")
    elif promo.type == "discount":
        await set_user_pending_promo(user_id, code)
        await message.answer(
            f"✅ Промокод сохранён!\n\n"
            f"Скидка <b>{promo.value:g}%</b> применится при следующей покупке тарифа. "
            f"Нажми <b>💎 Тарифы</b> и выбери нужный."
        )
    else:
        await message.answer("❌ Неизвестный тип промокода. Сообщи администратору.")


# ------------ Админ-команды ------------

@router.message(Command("promo"))
async def cmd_promo(message: Message) -> None:
    if not _is_admin(message):
        return
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer(
            "<b>Управление промокодами</b>\n\n"
            "<code>/promo new CODE discount PERCENT [max_uses] [expires_days]</code>\n"
            "<code>/promo new CODE trial DAYS TIER [max_uses] [expires_days]</code>\n"
            "<code>/promo list</code>\n"
            "<code>/promo del CODE</code>\n\n"
            "Примеры:\n"
            "<code>/promo new WELCOME20 discount 20 100 30</code>\n"
            "<code>/promo new TRIAL3 trial 3 base 50 14</code>"
        )
        return
    sub = parts[1].lower()
    if sub == "list":
        promos = await list_promos()
        if not promos:
            await message.answer("Промокодов пока нет.")
            return
        lines = ["<b>Промокоды:</b>"]
        for p in promos:
            expiry = p.expires_at.strftime("%Y-%m-%d") if p.expires_at else "∞"
            uses = f"{p.uses_count}/{p.max_uses}" if p.max_uses else f"{p.uses_count}/∞"
            if p.type == "discount":
                meta = f"скидка {p.value:g}%"
            else:
                meta = f"trial {int(p.value)}д {p.tier or 'base'}"
            lines.append(f"• <code>{p.code}</code> — {meta}, использовано {uses}, до {expiry}")
        await message.answer("\n".join(lines))
        return
    if sub == "del":
        if len(parts) < 3:
            await message.answer("Использование: <code>/promo del CODE</code>")
            return
        ok = await delete_promo(parts[2])
        await message.answer("✅ Удалён." if ok else "❌ Не найден.")
        return
    if sub == "new":
        if len(parts) < 5:
            await message.answer(
                "Не хватает аргументов. См. <code>/promo</code> без аргументов."
            )
            return
        code = parts[2]
        type_ = parts[3].lower()
        if type_ not in ("discount", "trial"):
            await message.answer("❌ Тип: discount или trial")
            return
        try:
            value = float(parts[4])
        except ValueError:
            await message.answer("❌ Value должно быть числом.")
            return
        tier = None
        rest = parts[5:]
        if type_ == "trial":
            if not rest:
                await message.answer("❌ Для trial нужен тариф: base, standart, pro или premium")
                return
            tier = rest[0].lower()
            if tier not in PAID_TIERS:
                await message.answer(f"❌ Тариф должен быть один из: {', '.join(PAID_TIERS)}")
                return
            rest = rest[1:]
        max_uses = int(rest[0]) if rest else 0
        expires_days = int(rest[1]) if len(rest) > 1 else None
        try:
            promo = await create_promo(code, type_, value, tier, max_uses, expires_days)
        except Exception as e:
            logger.warning(f"create_promo failed: {e}")
            await message.answer(f"❌ Не удалось создать: {e}")
            return
        await message.answer(f"✅ Промокод <code>{promo.code}</code> создан.")
        return
    await message.answer("Неизвестная команда. См. <code>/promo</code> без аргументов.")
