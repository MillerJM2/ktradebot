"""Обработчики команд Telegram-бота."""
from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from config import ADMIN_TELEGRAM_ID, DEFAULT_SPREAD_THRESHOLD


router = Router()


class BotState:
    """Простое хранилище состояния в памяти (на этапе MVP без БД)."""
    threshold: float = DEFAULT_SPREAD_THRESHOLD
    paused: bool = False


state = BotState()


def _is_admin(message: Message) -> bool:
    return message.from_user is not None and message.from_user.id == ADMIN_TELEGRAM_ID


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    if not _is_admin(message):
        await message.answer("⛔ Доступ ограничен (MVP-режим: только админ).")
        return
    await message.answer(
        "👋 Привет! Я бот для поиска межбиржевых арбитражных вилок.\n\n"
        "Команды:\n"
        "/status — текущие настройки\n"
        "/setthreshold N — поставить порог спреда в N%\n"
        "/pause — остановить рассылку сигналов\n"
        "/resume — возобновить рассылку"
    )


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    if not _is_admin(message):
        return
    paused_str = "на паузе ⏸" if state.paused else "активен ✅"
    await message.answer(
        f"Статус: {paused_str}\n"
        f"Порог спреда: {state.threshold}%"
    )


@router.message(Command("setthreshold"))
async def cmd_setthreshold(message: Message) -> None:
    if not _is_admin(message):
        return
    parts = message.text.split() if message.text else []
    if len(parts) != 2:
        await message.answer("Использование: /setthreshold 3")
        return
    try:
        new_threshold = float(parts[1])
    except ValueError:
        await message.answer("❌ Нужно число, например: /setthreshold 2.5")
        return
    if new_threshold <= 0 or new_threshold > 100:
        await message.answer("❌ Порог должен быть от 0 до 100")
        return
    state.threshold = new_threshold
    await message.answer(f"✅ Порог установлен: {new_threshold}%")


@router.message(Command("pause"))
async def cmd_pause(message: Message) -> None:
    if not _is_admin(message):
        return
    state.paused = True
    await message.answer("⏸ Рассылка приостановлена. /resume — возобновить.")


@router.message(Command("resume"))
async def cmd_resume(message: Message) -> None:
    if not _is_admin(message):
        return
    state.paused = False
    await message.answer("✅ Рассылка возобновлена.")
