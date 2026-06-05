"""Админская рассылка: /broadcast → отправить сообщение → подтверждение → копирование всем."""
import asyncio

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from loguru import logger

from bot.admins import is_admin as _is_admin_uid
from database.users_repo import list_users


router = Router()


_pending: dict[int, dict] = {}


def _is_admin(message_or_callback) -> bool:
    user = message_or_callback.from_user
    return user is not None and _is_admin_uid(user.id)


def _waiting_for_content(message: Message) -> bool:
    if not _is_admin(message):
        return False
    state = _pending.get(message.from_user.id)
    return bool(state and state.get("step") == "await_content")


@router.message(Command("broadcast"))
@router.message(F.text == "📢 Рассылка")
async def cmd_broadcast(message: Message) -> None:
    if not _is_admin(message):
        return
    _pending[message.from_user.id] = {"step": "await_content"}
    await message.answer(
        "📢 <b>Режим рассылки</b>\n\n"
        "Отправь сообщение для рассылки всем пользователям.\n"
        "Поддерживается текст, фото с подписью, видео, и т.д.\n\n"
        "Для отмены — /cancel"
    )


@router.message(Command("cancel"))
async def cmd_cancel(message: Message) -> None:
    if not _is_admin(message):
        return
    if _pending.pop(message.from_user.id, None):
        await message.answer("❌ Рассылка отменена.")


@router.message(_waiting_for_content)
async def handle_broadcast_content(message: Message) -> None:
    _pending[message.from_user.id] = {
        "step": "await_confirm",
        "from_chat_id": message.chat.id,
        "message_id": message.message_id,
    }
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Отправить всем", callback_data="bcast_send")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="bcast_cancel")],
    ])
    await message.reply(
        "👆 Вот так пользователи увидят сообщение.\nОтправить?",
        reply_markup=kb,
    )


@router.callback_query(F.data == "bcast_cancel")
async def cb_bcast_cancel(callback: CallbackQuery) -> None:
    if not _is_admin(callback):
        await callback.answer()
        return
    _pending.pop(callback.from_user.id, None)
    await callback.answer("Отменено")
    await callback.message.answer("❌ Рассылка отменена.")


@router.callback_query(F.data == "bcast_send")
async def cb_bcast_send(callback: CallbackQuery, bot: Bot) -> None:
    if not _is_admin(callback):
        await callback.answer()
        return
    state = _pending.pop(callback.from_user.id, None)
    if not state or state.get("step") != "await_confirm":
        await callback.answer("Нечего отправлять")
        return
    from_chat_id = state["from_chat_id"]
    message_id = state["message_id"]
    await callback.answer()
    progress = await callback.message.answer("📤 Начинаю рассылку...")

    users = await list_users()
    sent = 0
    blocked = 0
    failed = 0
    for u in users:
        try:
            await bot.copy_message(
                chat_id=u.telegram_id,
                from_chat_id=from_chat_id,
                message_id=message_id,
            )
            sent += 1
        except Exception as e:
            msg = str(e).lower()
            if "blocked" in msg or "chat not found" in msg or "user is deactivated" in msg:
                blocked += 1
            else:
                failed += 1
                logger.warning(f"broadcast to {u.telegram_id} failed: {e}")
        await asyncio.sleep(0.05)

    await progress.edit_text(
        f"📊 <b>Итоги рассылки</b>\n\n"
        f"👥 Всего: <b>{len(users)}</b>\n"
        f"✅ Доставлено: <b>{sent}</b>\n"
        f"🚫 Заблокировали бота: <b>{blocked}</b>\n"
        f"⚠️ Ошибки: <b>{failed}</b>"
    )
