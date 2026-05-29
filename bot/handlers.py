"""Обработчики команд и кнопок Telegram-бота."""
from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
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
BTN_THRESHOLD = "🎯 Порог спреда"
BTN_DIAG = "🔍 Диагностика"

BTN_ABOUT = "ℹ️ О боте"
BTN_TARIFFS = "💎 Тарифы"
BTN_REFERRAL = "🔗 Реферальная система"
BTN_SUPPORT = "💼 Техническая поддержка"


ADMIN_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=BTN_STATUS)],
        [KeyboardButton(text=BTN_THRESHOLD)],
        [KeyboardButton(text=BTN_PAUSE)],
        [KeyboardButton(text=BTN_RESUME)],
        [KeyboardButton(text=BTN_DIAG)],
    ],
    resize_keyboard=True,
)

USER_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=BTN_ABOUT)],
        [KeyboardButton(text=BTN_TARIFFS)],
        [KeyboardButton(text=BTN_REFERRAL)],
        [KeyboardButton(text=BTN_SUPPORT)],
    ],
    resize_keyboard=True,
)


def _is_admin(message: Message) -> bool:
    return message.from_user is not None and message.from_user.id == ADMIN_TELEGRAM_ID


def _keyboard_for(message: Message) -> ReplyKeyboardMarkup:
    return ADMIN_KEYBOARD if _is_admin(message) else USER_KEYBOARD


async def _deny(message: Message) -> None:
    await message.answer(
        "⛔ Эта команда доступна только администратору.",
        reply_markup=USER_KEYBOARD,
    )


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    if _is_admin(message):
        await message.answer(
            "👋 Привет, админ! Бот ищет вилки на 6 биржах.\n\n"
            "Используй кнопки внизу или команды:\n"
            "/status — текущие настройки\n"
            "/setthreshold N — порог спреда в %\n"
            "/pause /resume — пауза/запуск\n"
            "/diag — быстрая диагностика",
            reply_markup=ADMIN_KEYBOARD,
        )
        return
    await message.answer(
        "👋 Привет! Это бот для поиска <b>арбитражных вилок</b> между биржами.\n\n"
        "Сейчас бот находится в закрытом тестировании. "
        "Скоро откроется регистрация — выбирай раздел ниже, чтобы узнать подробности.",
        reply_markup=USER_KEYBOARD,
    )


@router.message(F.text == BTN_ABOUT)
async def btn_about(message: Message) -> None:
    await message.answer(
        "<b>О боте</b>\n\n"
        "Бот отслеживает цены топ-100 криптовалют на 6 крупнейших биржах "
        "(Binance, Bybit, OKX, KuCoin, Gate.io, MEXC) "
        "и присылает уведомления о выгодных межбиржевых вилках.\n\n"
        "Возможности:\n"
        "• Реалтайм сигналы 24/7\n"
        "• Настройка минимального спреда\n"
        "• Учёт торговых комиссий\n"
        "• Прямые ссылки на торговые страницы",
        reply_markup=USER_KEYBOARD,
    )


@router.message(F.text == BTN_TARIFFS)
async def btn_tariffs(message: Message) -> None:
    await message.answer(
        "<b>💎 Тарифы</b>\n\n"
        "🆓 <b>Free</b> — 2 биржи, спред от 5%, задержка 5 мин\n"
        "🥉 <b>Basic</b> — 4 биржи, спред от 2%, реалтайм — <b>$15/мес</b>\n"
        "🥈 <b>Pro</b> — все 6 бирж, спред от 0.5% — <b>$40/мес</b>\n"
        "🥇 <b>VIP</b> — Pro + автоторговля — <b>$100/мес</b>\n\n"
        "⏳ Подписка пока недоступна — мы готовим запуск.",
        reply_markup=USER_KEYBOARD,
    )


@router.message(F.text == BTN_REFERRAL)
async def btn_referral(message: Message) -> None:
    await message.answer(
        "<b>🔗 Реферальная система</b>\n\n"
        "Скоро ты сможешь приглашать друзей и получать "
        "<b>20% от их подписок</b> на свой баланс.\n\n"
        "⏳ Раздел в разработке.",
        reply_markup=USER_KEYBOARD,
    )


@router.message(F.text == BTN_SUPPORT)
async def btn_support(message: Message) -> None:
    await message.answer(
        "<b>💼 Техническая поддержка</b>\n\n"
        "По любым вопросам пиши: @harisov102",
        reply_markup=USER_KEYBOARD,
    )


@router.message(Command("status"))
@router.message(F.text == BTN_STATUS)
async def cmd_status(message: Message) -> None:
    if not _is_admin(message):
        await _deny(message)
        return
    paused_str = "на паузе ⏸" if state.paused else "активен ✅"
    await message.answer(
        f"<b>Статус бота</b>\n\n"
        f"Состояние: {paused_str}\n"
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
        f"<code>/setthreshold 1.5</code>",
        reply_markup=ADMIN_KEYBOARD,
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
    await message.answer(
        "Используй кнопки меню ниже 👇",
        reply_markup=_keyboard_for(message),
    )
