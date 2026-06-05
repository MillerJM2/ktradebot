"""Авто-публикация сигналов в Telegram-канал с контролем админа."""
import asyncio
from datetime import datetime, timedelta

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
from bot.runtime import runtime
from config import ADMIN_TELEGRAM_ID, CHANNEL_URL
from database.settings_repo import (
    get_bool,
    get_float,
    get_int,
    get_setting,
    set_setting,
)


router = Router()


# in-memory anti-duplicate: (symbol, buy, sell) → last proposed timestamp
_recently_proposed: dict[tuple[str, str, str], datetime] = {}
_lock = asyncio.Lock()


def _is_admin(message_or_callback) -> bool:
    user = message_or_callback.from_user
    return user is not None and _is_admin_uid(user.id)


async def _channel_id() -> str | None:
    return await get_setting("channel_id")


async def _channel_enabled() -> bool:
    return await get_bool("channel_enabled", False)


async def _auto_publish() -> bool:
    return await get_bool("channel_auto_publish", False)


async def _min_profit() -> float:
    return await get_float("channel_min_profit", 3.0)


async def _interval_minutes() -> int:
    return max(1, await get_int("channel_interval_minutes", 10))


def _format_for_channel(spread, base_text: str) -> str:
    bot_un = runtime.bot_username or "your_bot"
    return (
        f"{base_text}\n\n"
        f"👉 <a href=\"https://t.me/{bot_un}\">Получай сигналы 24/7 в боте</a>"
    )


def _admin_preview_kb(symbol: str, buy: str, sell: str) -> InlineKeyboardMarkup:
    cb_pub = f"chpub:{symbol}|{buy}|{sell}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📤 Опубликовать", callback_data=cb_pub),
            InlineKeyboardButton(text="❌ Пропустить", callback_data="chskip"),
        ],
    ])


def _cleanup_recent(interval: timedelta) -> None:
    now = datetime.utcnow()
    stale = [k for k, ts in _recently_proposed.items() if now - ts > interval * 2]
    for k in stale:
        _recently_proposed.pop(k, None)


async def try_propose(bot: Bot, spread, base_text: str) -> None:
    """Вызывается из arbitrage_loop для каждого верифицированного сигнала."""
    async with _lock:
        if not await _channel_enabled():
            return
        if spread.net_profit_percent < await _min_profit():
            return

        key = (spread.symbol, spread.buy_exchange, spread.sell_exchange)
        interval = timedelta(minutes=await _interval_minutes())
        _cleanup_recent(interval)

        last_ts = _recently_proposed.get(key)
        if last_ts and (datetime.utcnow() - last_ts) < interval:
            return
        _recently_proposed[key] = datetime.utcnow()

        chat_id = await _channel_id()
        channel_text = _format_for_channel(spread, base_text)

        if await _auto_publish():
            if not chat_id:
                logger.warning("auto_publish on but channel_id empty")
                return
            try:
                await bot.send_message(chat_id, channel_text, disable_web_page_preview=True)
            except Exception as e:
                logger.warning(f"channel auto-publish failed: {e}")
            return

        from bot.admins import known_admin_ids
        for admin_id in known_admin_ids():
            try:
                await bot.send_message(
                    admin_id,
                    f"📺 <b>Кандидат на публикацию в канале</b>\n\n{channel_text}",
                    reply_markup=_admin_preview_kb(*key),
                    disable_web_page_preview=True,
                )
            except Exception as e:
                logger.warning(f"admin preview to {admin_id} failed: {e}")


@router.callback_query(F.data == "chskip")
async def cb_skip(callback: CallbackQuery) -> None:
    if not _is_admin(callback):
        await callback.answer()
        return
    await callback.answer("Пропущено")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.reply("❌ Сигнал пропущен.")
    except Exception:
        pass


@router.callback_query(F.data.startswith("chpub:"))
async def cb_publish(callback: CallbackQuery, bot: Bot) -> None:
    if not _is_admin(callback):
        await callback.answer()
        return
    chat_id = await _channel_id()
    if not chat_id:
        await callback.answer("Канал не настроен")
        await callback.message.reply(
            "❌ Сначала настрой канал: <code>/channel set @your_channel</code> "
            "или <code>/channel set -1001234567890</code>"
        )
        return
    try:
        await bot.copy_message(
            chat_id=chat_id,
            from_chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
        )
    except Exception as e:
        logger.warning(f"publish to channel failed: {e}")
        await callback.answer("Ошибка")
        await callback.message.reply(f"❌ Не удалось опубликовать: {e}")
        return
    await callback.answer("Опубликовано")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.reply("✅ Опубликовано в канал.")
    except Exception:
        pass


# ------------ Админ-команды ------------

@router.message(Command("channel"))
async def cmd_channel(message: Message) -> None:
    if not _is_admin(message):
        return
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 2:
        cid = await _channel_id() or "не задан"
        enabled = "✅ включён" if await _channel_enabled() else "❌ выключен"
        auto = "✅ авто" if await _auto_publish() else "🤚 ручной (превью админу)"
        min_p = await _min_profit()
        interval = await _interval_minutes()
        await message.answer(
            f"<b>📺 Настройки канала</b>\n\n"
            f"Канал: <code>{cid}</code>\n"
            f"Статус: {enabled}\n"
            f"Режим: {auto}\n"
            f"Мин. чистый профит: <b>{min_p:g}%</b>\n"
            f"Интервал между публикациями: <b>{interval} мин</b>\n\n"
            f"<b>Команды:</b>\n"
            f"<code>/channel set @username</code> — указать канал\n"
            f"<code>/channel set -1001234567890</code> — по chat_id\n"
            f"<code>/channel enable</code> / <code>disable</code>\n"
            f"<code>/channel auto on</code> / <code>off</code>\n"
            f"<code>/channel min 3.5</code> — мин. профит, %\n"
            f"<code>/channel interval 10</code> — мин. интервал, минут\n"
            f"<code>/channel test</code> — отправить тестовое сообщение в канал"
        )
        return

    sub = parts[1].lower()
    arg = parts[2] if len(parts) > 2 else ""

    if sub == "set":
        if not arg:
            await message.answer("Использование: <code>/channel set @username</code> или <code>chat_id</code>")
            return
        await set_setting("channel_id", arg.strip())
        await message.answer(f"✅ Канал установлен: <code>{arg.strip()}</code>")
    elif sub == "enable":
        await set_setting("channel_enabled", "true")
        await message.answer("✅ Публикации в канал включены.")
    elif sub == "disable":
        await set_setting("channel_enabled", "false")
        await message.answer("⏸ Публикации в канал выключены.")
    elif sub == "auto":
        on = arg.lower() in ("on", "true", "1", "yes")
        await set_setting("channel_auto_publish", "true" if on else "false")
        await message.answer(
            "🚀 Авто-публикация включена (без подтверждения)." if on
            else "🤚 Авто выключена — буду слать превью на подтверждение."
        )
    elif sub == "min":
        try:
            val = float(arg)
        except ValueError:
            await message.answer("❌ Нужно число, например <code>/channel min 3.5</code>")
            return
        await set_setting("channel_min_profit", str(val))
        await message.answer(f"✅ Минимальный профит: <b>{val:g}%</b>")
    elif sub == "interval":
        try:
            val = int(arg)
        except ValueError:
            await message.answer("❌ Нужно целое число минут, например <code>/channel interval 10</code>")
            return
        await set_setting("channel_interval_minutes", str(val))
        await message.answer(f"✅ Интервал: <b>{val} мин</b>")
    elif sub == "test":
        chat_id = await _channel_id()
        if not chat_id:
            await message.answer("❌ Канал не задан.")
            return
        try:
            await message.bot.send_message(
                chat_id,
                "🧪 Тестовое сообщение от KTradeClub.\n"
                "Если ты это видишь — настройка канала прошла успешно.",
            )
            await message.answer("✅ Отправил.")
        except Exception as e:
            await message.answer(f"❌ Ошибка: {e}\n\nУбедись, что бот добавлен в канал как админ.")
    else:
        await message.answer("Неизвестная подкоманда. /channel — справка.")
