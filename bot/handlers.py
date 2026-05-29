"""Обработчики команд и кнопок Telegram-бота."""
from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from config import ADMIN_TELEGRAM_ID, DEFAULT_SPREAD_THRESHOLD


router = Router()


class BotState:
    """Простое хранилище состояния в памяти (на этапе MVP без БД)."""
    threshold: float = DEFAULT_SPREAD_THRESHOLD
    paused: bool = False


state = BotState()


BTN_STATUS = "📊 Статус"
BTN_PAUSE = "⏸ Пауза"
BTN_RESUME = "▶️ Запустить"
BTN_THRESHOLD = "🎯 Порог"
BTN_DIAG = "🔍 Диагностика"

ADMIN_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=BTN_STATUS), KeyboardButton(text=BTN_THRESHOLD)],
        [KeyboardButton(text=BTN_PAUSE), KeyboardButton(text=BTN_RESUME)],
        [KeyboardButton(text=BTN_DIAG)],
    ],
    resize_keyboard=True,
)


def _is_admin(message: Message) -> bool:
    return message.from_user is not None and message.from_user.id == ADMIN_TELEGRAM_ID


async def _deny(message: Message) -> None:
    await message.answer(
        "⛔ У тебя нет доступа к этой команде.\n"
        "Бот пока работает в закрытом режиме.",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    if not _is_admin(message):
        await message.answer(
            "👋 Привет! Этот бот ищет арбитражные вилки между биржами.\n\n"
            "Сейчас он в закрытом тестировании. Скоро откроется набор подписчиков — "
            "следи за обновлениями."
        )
        return
    await message.answer(
        "👋 Привет, админ! Бот ищет вилки на 6 биржах.\n\n"
        "Используй кнопки внизу или команды:\n"
        "/status — текущие настройки\n"
        "/setthreshold N — порог спреда в %\n"
        "/pause /resume — пауза/запуск\n"
        "/diag — быстрая диагностика",
        reply_markup=ADMIN_KEYBOARD,
    )


@router.message(Command("status"))
@router.message(F.text == BTN_STATUS)
async def cmd_status(message: Message) -> None:
    if not _is_admin(message):
        await _deny(message)
        return
    paused_str = "на паузе ⏸" if state.paused else "активен ✅"
    await message.answer(
        f"Статус: {paused_str}\n"
        f"Порог спреда: <b>{state.threshold}%</b>",
        reply_markup=ADMIN_KEYBOARD,
    )


@router.message(Command("setthreshold"))
async def cmd_setthreshold(message: Message) -> None:
    if not _is_admin(message):
        await _deny(message)
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
    await message.answer(
        f"✅ Порог установлен: <b>{new_threshold}%</b>",
        reply_markup=ADMIN_KEYBOARD,
    )


@router.message(F.text == BTN_THRESHOLD)
async def btn_threshold(message: Message) -> None:
    if not _is_admin(message):
        await _deny(message)
        return
    await message.answer(
        f"Текущий порог: <b>{state.threshold}%</b>\n\n"
        f"Чтобы изменить — отправь команду:\n"
        f"<code>/setthreshold 1.5</code>"
    )


@router.message(Command("pause"))
@router.message(F.text == BTN_PAUSE)
async def cmd_pause(message: Message) -> None:
    if not _is_admin(message):
        await _deny(message)
        return
    state.paused = True
    await message.answer("⏸ Рассылка приостановлена.", reply_markup=ADMIN_KEYBOARD)


@router.message(Command("resume"))
@router.message(F.text == BTN_RESUME)
async def cmd_resume(message: Message) -> None:
    if not _is_admin(message):
        await _deny(message)
        return
    state.paused = False
    await message.answer("✅ Рассылка возобновлена.", reply_markup=ADMIN_KEYBOARD)


@router.message(Command("diag"))
@router.message(F.text == BTN_DIAG)
async def cmd_diag(message: Message) -> None:
    if not _is_admin(message):
        await _deny(message)
        return
    from exchanges.fetcher import fetch_all_tickers
    from arbitrage.finder import find_spreads

    await message.answer("🔍 Запускаю один цикл опроса бирж...")
    tickers = await fetch_all_tickers()
    counts = {ex: len(t) for ex, t in tickers.items()}
    spreads_at_threshold = find_spreads(tickers, state.threshold)
    spreads_top = find_spreads(tickers, 0.0)

    lines = ["<b>Тикеры по биржам:</b>"]
    for ex, n in counts.items():
        emoji = "✅" if n > 0 else "❌"
        lines.append(f"{emoji} {ex}: {n}")

    lines.append("")
    lines.append(f"Вилок ≥ {state.threshold}%: <b>{len(spreads_at_threshold)}</b>")
    lines.append(f"Всего пар с положительным спредом: <b>{len(spreads_top)}</b>")

    if spreads_top:
        lines.append("")
        lines.append("<b>Топ-5 максимальных спредов:</b>")
        for sp in spreads_top[:5]:
            lines.append(
                f"• {sp.symbol}: {sp.spread_percent:.2f}% "
                f"({sp.buy_exchange} → {sp.sell_exchange})"
            )

    await message.answer("\n".join(lines), reply_markup=ADMIN_KEYBOARD)


@router.message()
async def fallback(message: Message) -> None:
    if not _is_admin(message):
        await message.answer(
            "ℹ️ Бот пока в закрытом режиме. Команды недоступны."
        )
        return
    await message.answer(
        "Не понял команду. Используй кнопки или /status, /diag, /setthreshold, /pause, /resume.",
        reply_markup=ADMIN_KEYBOARD,
    )
