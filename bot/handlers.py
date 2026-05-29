"""Обработчики команд и кнопок Telegram-бота (multi-user через SQLite)."""
from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup

from config import ADMIN_TELEGRAM_ID
from database.users_repo import (
    count_users,
    get_or_create_user,
    set_paused,
    set_threshold,
)


router = Router()


BTN_STATUS = "📊 Статус"
BTN_PAUSE = "⏸ Пауза"
BTN_RESUME = "▶️ Запустить"
BTN_THRESHOLD = "🎯 Порог спреда"
BTN_DIAG = "🔍 Диагностика"

BTN_ABOUT = "ℹ️ О боте"
BTN_TARIFFS = "💎 Тарифы"
BTN_REFERRAL = "🔗 Реферальная система"
BTN_SUPPORT = "💼 Техническая поддержка"


def _user_keyboard(is_admin: bool) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=BTN_STATUS)],
        [KeyboardButton(text=BTN_THRESHOLD)],
        [KeyboardButton(text=BTN_PAUSE)],
        [KeyboardButton(text=BTN_RESUME)],
        [KeyboardButton(text=BTN_ABOUT)],
        [KeyboardButton(text=BTN_TARIFFS)],
        [KeyboardButton(text=BTN_REFERRAL)],
        [KeyboardButton(text=BTN_SUPPORT)],
    ]
    if is_admin:
        rows.append([KeyboardButton(text=BTN_DIAG)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def _is_admin(message: Message) -> bool:
    return message.from_user is not None and message.from_user.id == ADMIN_TELEGRAM_ID


async def _kb(message: Message) -> ReplyKeyboardMarkup:
    return _user_keyboard(_is_admin(message))


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    user = await get_or_create_user(
        message.from_user.id,
        message.from_user.username,
    )
    is_admin = _is_admin(message)
    greeting = "админ" if is_admin else message.from_user.first_name or "друг"
    await message.answer(
        f"👋 Привет, {greeting}!\n\n"
        f"Это бот для поиска <b>арбитражных вилок</b> между биржами "
        f"Binance, Bybit, OKX, KuCoin, Gate.io, MEXC.\n\n"
        f"Сейчас твой <b>порог спреда: {user.threshold}%</b>. "
        f"Сигналы рассылаются в реалтайме при появлении вилок выше порога.\n\n"
        f"Используй кнопки внизу 👇",
        reply_markup=_user_keyboard(is_admin),
    )


@router.message(Command("status"))
@router.message(F.text == BTN_STATUS)
async def cmd_status(message: Message) -> None:
    user = await get_or_create_user(
        message.from_user.id, message.from_user.username
    )
    paused_str = "на паузе ⏸" if user.paused else "активен ✅"
    text = (
        f"<b>Твой статус</b>\n\n"
        f"Состояние: {paused_str}\n"
        f"Порог спреда: <b>{user.threshold}%</b>\n"
        f"Тариф: <b>{user.tier}</b>"
    )
    if _is_admin(message):
        total = await count_users()
        text += f"\n\n👥 Всего пользователей: {total}"
    await message.answer(text, reply_markup=await _kb(message))


@router.message(Command("setthreshold"))
async def cmd_setthreshold(message: Message) -> None:
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
    await get_or_create_user(message.from_user.id, message.from_user.username)
    await set_threshold(message.from_user.id, new_threshold)
    await message.answer(
        f"✅ Твой порог установлен: <b>{new_threshold}%</b>",
        reply_markup=await _kb(message),
    )


@router.message(F.text == BTN_THRESHOLD)
async def btn_threshold(message: Message) -> None:
    user = await get_or_create_user(
        message.from_user.id, message.from_user.username
    )
    await message.answer(
        f"Твой текущий порог: <b>{user.threshold}%</b>\n\n"
        f"Чтобы изменить — отправь команду:\n"
        f"<code>/setthreshold 1.5</code>",
        reply_markup=await _kb(message),
    )


@router.message(Command("pause"))
@router.message(F.text == BTN_PAUSE)
async def cmd_pause(message: Message) -> None:
    await get_or_create_user(message.from_user.id, message.from_user.username)
    await set_paused(message.from_user.id, True)
    await message.answer(
        "⏸ Рассылка тебе приостановлена. Нажми «▶️ Запустить» для возобновления.",
        reply_markup=await _kb(message),
    )


@router.message(Command("resume"))
@router.message(F.text == BTN_RESUME)
async def cmd_resume(message: Message) -> None:
    await get_or_create_user(message.from_user.id, message.from_user.username)
    await set_paused(message.from_user.id, False)
    await message.answer(
        "✅ Рассылка возобновлена.",
        reply_markup=await _kb(message),
    )


@router.message(F.text == BTN_ABOUT)
async def btn_about(message: Message) -> None:
    await message.answer(
        "<b>О боте</b>\n\n"
        "Бот отслеживает цены криптовалют на 6 крупнейших биржах "
        "(Binance, Bybit, OKX, KuCoin, Gate.io, MEXC) и присылает "
        "уведомления о выгодных межбиржевых вилках.\n\n"
        "Возможности:\n"
        "• Реалтайм сигналы 24/7\n"
        "• Индивидуальный порог спреда\n"
        "• Учёт торговых комиссий\n"
        "• Прямые ссылки на торговые страницы",
        reply_markup=await _kb(message),
    )


@router.message(F.text == BTN_TARIFFS)
async def btn_tariffs(message: Message) -> None:
    await message.answer(
        "<b>💎 Тарифы</b>\n\n"
        "🆓 <b>Free</b> — 2 биржи, спред от 5%, задержка 5 мин\n"
        "🥉 <b>Basic</b> — 4 биржи, спред от 2%, реалтайм — <b>$15/мес</b>\n"
        "🥈 <b>Pro</b> — все 6 бирж, спред от 0.5% — <b>$40/мес</b>\n"
        "🥇 <b>VIP</b> — Pro + автоторговля — <b>$100/мес</b>\n\n"
        "⏳ Подписка пока недоступна — готовим запуск.",
        reply_markup=await _kb(message),
    )


@router.message(F.text == BTN_REFERRAL)
async def btn_referral(message: Message) -> None:
    await message.answer(
        "<b>🔗 Реферальная система</b>\n\n"
        "Скоро ты сможешь приглашать друзей и получать "
        "<b>20% от их подписок</b> на свой баланс.\n\n"
        "⏳ Раздел в разработке.",
        reply_markup=await _kb(message),
    )


@router.message(F.text == BTN_SUPPORT)
async def btn_support(message: Message) -> None:
    await message.answer(
        "<b>💼 Техническая поддержка</b>\n\n"
        "По любым вопросам пиши: @harisov102",
        reply_markup=await _kb(message),
    )


@router.message(Command("diag"))
@router.message(F.text == BTN_DIAG)
async def cmd_diag(message: Message) -> None:
    if not _is_admin(message):
        await message.answer(
            "⛔ Эта команда доступна только администратору.",
            reply_markup=await _kb(message),
        )
        return
    from exchanges.fetcher import fetch_all_tickers
    from arbitrage.finder import find_spreads

    user = await get_or_create_user(message.from_user.id, message.from_user.username)
    await message.answer("🔍 Запускаю один цикл опроса бирж...")
    tickers = await fetch_all_tickers()
    counts = {ex: len(t) for ex, t in tickers.items()}
    spreads_at_threshold = find_spreads(tickers, user.threshold)
    spreads_top = find_spreads(tickers, 0.0)

    lines = ["<b>Тикеры по биржам:</b>"]
    for ex, n in counts.items():
        emoji = "✅" if n > 0 else "❌"
        lines.append(f"{emoji} {ex}: {n}")

    lines.append("")
    lines.append(f"Вилок ≥ {user.threshold}%: <b>{len(spreads_at_threshold)}</b>")
    lines.append(f"Всего пар с положительным спредом: <b>{len(spreads_top)}</b>")

    if spreads_top:
        lines.append("")
        lines.append("<b>Топ-5 максимальных спредов:</b>")
        for sp in spreads_top[:5]:
            lines.append(
                f"• {sp.symbol}: {sp.spread_percent:.2f}% "
                f"({sp.buy_exchange} → {sp.sell_exchange})"
            )

    await message.answer("\n".join(lines), reply_markup=await _kb(message))


@router.message()
async def fallback(message: Message) -> None:
    await get_or_create_user(message.from_user.id, message.from_user.username)
    await message.answer(
        "Используй кнопки меню ниже 👇",
        reply_markup=await _kb(message),
    )
