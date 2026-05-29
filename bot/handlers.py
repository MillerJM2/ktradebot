"""Обработчики команд и кнопок Telegram-бота (multi-user + tiers)."""
from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from loguru import logger

from config import ADMIN_TELEGRAM_ID, SUBSCRIPTION_DAYS
from database.invoices_repo import create_invoice as save_invoice
from database.users_repo import (
    count_users,
    find_user_by_username,
    get_or_create_user,
    grant_subscription,
    list_users,
    revoke_subscription,
    set_paused,
    set_threshold,
)
from subscriptions.crypto_bot import (
    CryptoBotError,
    create_invoice,
    is_configured as cryptobot_configured,
)
from subscriptions.tiers import TIERS, effective_tier, features


router = Router()


BTN_CABINET = "👤 Личный кабинет"
BTN_ABOUT = "ℹ️ О боте"
BTN_TARIFFS = "💎 Тарифы"
BTN_REFERRAL = "🔗 Реферальная система"
BTN_SUPPORT = "💼 Техническая поддержка"
BTN_DIAG = "🔍 Диагностика"

BTN_STATUS = "📊 Статус"
BTN_THRESHOLD = "🎯 Порог спреда"
BTN_PAUSE = "⏸ Пауза"
BTN_RESUME = "▶️ Запустить"
BTN_BACK = "🔙 В главное меню"


def _main_keyboard(is_admin: bool) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=BTN_CABINET)],
        [KeyboardButton(text=BTN_TARIFFS)],
        [KeyboardButton(text=BTN_ABOUT)],
        [KeyboardButton(text=BTN_REFERRAL)],
        [KeyboardButton(text=BTN_SUPPORT)],
    ]
    if is_admin:
        rows.append([KeyboardButton(text=BTN_DIAG)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def _cabinet_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_STATUS)],
            [KeyboardButton(text=BTN_THRESHOLD)],
            [KeyboardButton(text=BTN_PAUSE)],
            [KeyboardButton(text=BTN_RESUME)],
            [KeyboardButton(text=BTN_BACK)],
        ],
        resize_keyboard=True,
    )


def _is_admin(message: Message) -> bool:
    return message.from_user is not None and message.from_user.id == ADMIN_TELEGRAM_ID


async def _kb(message: Message) -> ReplyKeyboardMarkup:
    return _main_keyboard(_is_admin(message))


def _format_expiry(dt) -> str:
    if dt is None:
        return "—"
    return dt.strftime("%Y-%m-%d %H:%M UTC")


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    user = await get_or_create_user(
        message.from_user.id, message.from_user.username
    )
    is_admin = _is_admin(message)
    tier_eff = effective_tier(user.tier, user.subscription_expires_at)
    feats = features(tier_eff)
    greeting = "админ" if is_admin else message.from_user.first_name or "друг"
    has_sub = tier_eff in ("basic", "pro", "vip", "admin")
    if has_sub:
        body = (
            f"Твой тариф: <b>{feats.name}</b>\n"
            f"Доступно бирж: {len(feats.allowed_exchanges)}\n"
            f"Минимальный порог: {feats.min_threshold}%"
        )
    else:
        body = (
            "У тебя пока <b>нет активной подписки</b>.\n"
            "Чтобы начать получать сигналы — выбери тариф в разделе "
            "<b>💎 Тарифы</b>."
        )
    await message.answer(
        f"👋 Привет, {greeting}!\n\n"
        f"Бот ищет <b>арбитражные вилки</b> на 6 биржах "
        f"(Binance, Bybit, OKX, KuCoin, Gate.io, MEXC).\n\n"
        f"{body}\n\n"
        f"Используй кнопки внизу 👇",
        reply_markup=_main_keyboard(is_admin),
    )


@router.message(F.text == BTN_CABINET)
async def btn_cabinet(message: Message) -> None:
    user = await get_or_create_user(
        message.from_user.id, message.from_user.username
    )
    tier_eff = effective_tier(user.tier, user.subscription_expires_at)
    feats = features(tier_eff)
    has_sub = tier_eff in ("basic", "pro", "vip", "admin")
    paused_str = "на паузе ⏸" if user.paused else "активен ✅"
    if has_sub:
        sub_line = (
            f"Тариф: <b>{feats.name}</b> до "
            f"{_format_expiry(user.subscription_expires_at)}"
        )
    else:
        sub_line = "Подписка: <b>нет активной</b>"
    await message.answer(
        f"👤 <b>Личный кабинет</b>\n\n"
        f"{sub_line}\n"
        f"Состояние: {paused_str}\n"
        f"Порог: {user.threshold}%\n\n"
        f"Используй кнопки ниже 👇",
        reply_markup=_cabinet_keyboard(),
    )


@router.message(F.text == BTN_BACK)
async def btn_back(message: Message) -> None:
    await message.answer(
        "🏠 Главное меню",
        reply_markup=_main_keyboard(_is_admin(message)),
    )


@router.message(Command("status"))
@router.message(F.text == BTN_STATUS)
async def cmd_status(message: Message) -> None:
    user = await get_or_create_user(
        message.from_user.id, message.from_user.username
    )
    tier_eff = effective_tier(user.tier, user.subscription_expires_at)
    feats = features(tier_eff)
    has_sub = tier_eff in ("basic", "pro", "vip", "admin")
    paused_str = "на паузе ⏸" if user.paused else "активен ✅"

    if has_sub:
        effective_threshold = max(user.threshold, feats.min_threshold)
        exchanges_line = ", ".join(feats.allowed_exchanges)
        text = (
            f"<b>Твой статус</b>\n\n"
            f"Состояние: {paused_str}\n"
            f"Тариф: <b>{feats.name}</b>\n"
            f"Подписка до: {_format_expiry(user.subscription_expires_at)}\n"
            f"\n"
            f"Твой порог: {user.threshold}%\n"
            f"Фактический порог (с учётом тарифа): <b>{effective_threshold}%</b>\n"
            f"Доступные биржи: {exchanges_line}"
        )
    else:
        text = (
            f"<b>Твой статус</b>\n\n"
            f"Подписка: <b>нет активной</b>\n"
            f"Состояние: {paused_str}\n\n"
            f"Чтобы начать получать сигналы — выбери тариф в разделе "
            f"<b>💎 Тарифы</b>."
        )
    if _is_admin(message):
        total = await count_users()
        text += f"\n\n👥 Всего пользователей: {total}"
    await message.answer(text, reply_markup=_cabinet_keyboard())


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
    user = await get_or_create_user(message.from_user.id, message.from_user.username)
    feats = features(effective_tier(user.tier, user.subscription_expires_at))
    await set_threshold(message.from_user.id, new_threshold)
    note = ""
    if new_threshold < feats.min_threshold:
        note = (
            f"\n\n⚠️ На твоём тарифе минимальный порог — <b>{feats.min_threshold}%</b>. "
            f"Сигналы будут приходить только от этого значения."
        )
    await message.answer(
        f"✅ Твой порог установлен: <b>{new_threshold}%</b>{note}",
        reply_markup=_cabinet_keyboard(),
    )


@router.message(F.text == BTN_THRESHOLD)
async def btn_threshold(message: Message) -> None:
    user = await get_or_create_user(
        message.from_user.id, message.from_user.username
    )
    feats = features(effective_tier(user.tier, user.subscription_expires_at))
    await message.answer(
        f"Твой текущий порог: <b>{user.threshold}%</b>\n"
        f"Минимум для твоего тарифа: <b>{feats.min_threshold}%</b>\n\n"
        f"Чтобы изменить — отправь команду:\n"
        f"<code>/setthreshold 1.5</code>",
        reply_markup=_cabinet_keyboard(),
    )


@router.message(Command("pause"))
@router.message(F.text == BTN_PAUSE)
async def cmd_pause(message: Message) -> None:
    await get_or_create_user(message.from_user.id, message.from_user.username)
    await set_paused(message.from_user.id, True)
    await message.answer(
        "⏸ Рассылка тебе приостановлена.",
        reply_markup=_cabinet_keyboard(),
    )


@router.message(Command("resume"))
@router.message(F.text == BTN_RESUME)
async def cmd_resume(message: Message) -> None:
    await get_or_create_user(message.from_user.id, message.from_user.username)
    await set_paused(message.from_user.id, False)
    await message.answer(
        "✅ Рассылка возобновлена.",
        reply_markup=_cabinet_keyboard(),
    )


@router.message(F.text == BTN_ABOUT)
async def btn_about(message: Message) -> None:
    await message.answer(
        "<b>О боте</b>\n\n"
        "Бот отслеживает цены криптовалют на 6 крупнейших биржах и присылает "
        "уведомления о <b>проверенных</b> межбиржевых вилках.\n\n"
        "Каждый сигнал проходит 4 фильтра:\n"
        "1. Вывод включён на бирже покупки\n"
        "2. Депозит включён на бирже продажи\n"
        "3. Есть общая работающая сеть\n"
        "4. Реальный спред по стакану + после комиссий ≥ порог",
        reply_markup=_main_keyboard(_is_admin(message)),
    )


def _tariff_inline_keyboard() -> InlineKeyboardMarkup | None:
    if not cryptobot_configured():
        return None
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"🥉 Купить Basic — ${TIERS['basic'].price_usd:g}",
            callback_data="buy:basic",
        )],
        [InlineKeyboardButton(
            text=f"🥈 Купить Pro — ${TIERS['pro'].price_usd:g}",
            callback_data="buy:pro",
        )],
        [InlineKeyboardButton(
            text=f"🥇 Купить VIP — ${TIERS['vip'].price_usd:g}",
            callback_data="buy:vip",
        )],
    ])


@router.message(F.text == BTN_TARIFFS)
async def btn_tariffs(message: Message) -> None:
    user = await get_or_create_user(
        message.from_user.id, message.from_user.username
    )
    tier_eff = effective_tier(user.tier, user.subscription_expires_at)
    has_sub = tier_eff in ("basic", "pro", "vip", "admin")
    lines = ["<b>💎 Тарифы</b>", ""]
    if has_sub:
        lines.append(f"Твой текущий: <b>{features(tier_eff).name}</b>")
        if user.subscription_expires_at:
            lines.append(f"Действует до: {_format_expiry(user.subscription_expires_at)}")
    else:
        lines.append("У тебя пока <b>нет активной подписки</b>.")
    lines.append("")
    for key in ("basic", "pro", "vip"):
        t = TIERS[key]
        prefix = "👉 " if key == tier_eff else "    "
        price = f"${t.price_usd:g}/мес"
        lines.append(
            f"{prefix}<b>{t.name}</b> — {price}\n"
            f"     {len(t.allowed_exchanges)} бирж, порог от {t.min_threshold}%, "
            f"до {t.max_signals_per_cycle} сигналов за цикл"
        )
    inline_kb = _tariff_inline_keyboard()
    if inline_kb is None:
        lines.append("")
        lines.append("⏳ Оплата через CryptoBot скоро будет доступна.")
    await message.answer(
        "\n".join(lines),
        reply_markup=_main_keyboard(_is_admin(message)),
    )
    if inline_kb is not None:
        await message.answer(
            "Выбери тариф для покупки на 30 дней:",
            reply_markup=inline_kb,
        )


@router.callback_query(F.data.startswith("buy:"))
async def cb_buy(callback: CallbackQuery) -> None:
    await callback.answer()
    tier = callback.data.split(":", 1)[1]
    if tier not in ("basic", "pro", "vip"):
        await callback.message.answer("❌ Неизвестный тариф.")
        return
    feats = features(tier)
    user = await get_or_create_user(
        callback.from_user.id, callback.from_user.username
    )
    try:
        invoice = await create_invoice(
            amount_usd=feats.price_usd,
            description=f"Подписка {feats.name} на {SUBSCRIPTION_DAYS} дней",
            payload=f"{user.telegram_id}:{tier}:{SUBSCRIPTION_DAYS}",
        )
    except CryptoBotError as e:
        logger.warning(f"createInvoice failed: {e}")
        await callback.message.answer(
            "❌ Не удалось создать счёт. Попробуй позже или напиши в поддержку."
        )
        return
    await save_invoice(
        invoice_id=int(invoice["invoice_id"]),
        user_id=user.telegram_id,
        tier=tier,
        days=SUBSCRIPTION_DAYS,
        amount_usd=feats.price_usd,
        pay_url=invoice["pay_url"],
    )
    pay_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Перейти к оплате", url=invoice["pay_url"])],
    ])
    await callback.message.answer(
        f"💳 <b>Счёт создан</b>\n\n"
        f"Тариф: <b>{feats.name}</b>\n"
        f"Сумма: <b>${feats.price_usd:g}</b> в USDT\n"
        f"Срок: {SUBSCRIPTION_DAYS} дней\n\n"
        f"Жми кнопку — оплата в @CryptoBot. После оплаты подписка активируется автоматически в течение минуты.",
        reply_markup=pay_kb,
    )


@router.message(F.text == BTN_REFERRAL)
async def btn_referral(message: Message) -> None:
    await message.answer(
        "<b>🔗 Реферальная система</b>\n\n"
        "Скоро ты сможешь приглашать друзей и получать "
        "<b>20% от их подписок</b> на свой баланс.\n\n"
        "⏳ Раздел в разработке.",
        reply_markup=_main_keyboard(_is_admin(message)),
    )


@router.message(F.text == BTN_SUPPORT)
async def btn_support(message: Message) -> None:
    await message.answer(
        "<b>💼 Техническая поддержка</b>\n\n"
        "⏳ Скоро здесь появится контакт поддержки.",
        reply_markup=_main_keyboard(_is_admin(message)),
    )


@router.message(Command("grant"))
async def cmd_grant(message: Message) -> None:
    if not _is_admin(message):
        return
    parts = (message.text or "").split()
    if len(parts) != 4:
        await message.answer(
            "Использование: <code>/grant &lt;user_id|@username&gt; &lt;tier&gt; &lt;days&gt;</code>\n"
            "Тарифы: free, basic, pro, vip\n"
            "Пример: <code>/grant @ivanov pro 30</code>"
        )
        return
    target, tier, days_str = parts[1], parts[2], parts[3]
    if tier not in ("free", "basic", "pro", "vip"):
        await message.answer("❌ Тариф должен быть: free, basic, pro, vip")
        return
    try:
        days = int(days_str)
    except ValueError:
        await message.answer("❌ Дней — целое число")
        return

    if target.startswith("@") or not target.lstrip("-").isdigit():
        u = await find_user_by_username(target)
    else:
        u = await get_or_create_user(int(target))
    if u is None:
        await message.answer("❌ Пользователь не найден. Он должен был хотя бы раз нажать /start.")
        return

    updated = await grant_subscription(u.telegram_id, tier, days)
    await message.answer(
        f"✅ {updated.username or updated.telegram_id} → "
        f"<b>{features(tier).name}</b> до {_format_expiry(updated.subscription_expires_at)}"
    )


@router.message(Command("revoke"))
async def cmd_revoke(message: Message) -> None:
    if not _is_admin(message):
        return
    parts = (message.text or "").split()
    if len(parts) != 2:
        await message.answer("Использование: <code>/revoke &lt;user_id|@username&gt;</code>")
        return
    target = parts[1]
    if target.startswith("@") or not target.lstrip("-").isdigit():
        u = await find_user_by_username(target)
    else:
        u = await get_or_create_user(int(target))
    if u is None:
        await message.answer("❌ Пользователь не найден.")
        return
    await revoke_subscription(u.telegram_id)
    await message.answer(f"✅ Подписка отозвана у {u.username or u.telegram_id}.")


@router.message(Command("users"))
async def cmd_users(message: Message) -> None:
    if not _is_admin(message):
        return
    users = await list_users()
    if not users:
        await message.answer("Пользователей пока нет.")
        return
    lines = [f"<b>Всего: {len(users)}</b>", ""]
    for u in users[:50]:
        tier_eff = effective_tier(u.tier, u.subscription_expires_at)
        line = f"• {u.username or u.telegram_id} — {features(tier_eff).name}"
        if u.subscription_expires_at:
            line += f" (до {u.subscription_expires_at:%Y-%m-%d})"
        if u.paused:
            line += " ⏸"
        lines.append(line)
    if len(users) > 50:
        lines.append(f"\n... и ещё {len(users) - 50}")
    await message.answer("\n".join(lines))


@router.message(Command("diag"))
@router.message(F.text == BTN_DIAG)
async def cmd_diag(message: Message) -> None:
    if not _is_admin(message):
        await message.answer(
            "⛔ Команда доступна только администратору.",
            reply_markup=await _kb(message),
        )
        return
    from exchanges.fetcher import fetch_all_tickers
    from arbitrage.finder import find_spreads

    user = await get_or_create_user(message.from_user.id, message.from_user.username)
    await message.answer("🔍 Запускаю один цикл опроса бирж...")
    tickers = await fetch_all_tickers()
    counts = {ex: len(t) for ex, t in tickers.items()}
    spreads_at = find_spreads(tickers, user.threshold)
    spreads_top = find_spreads(tickers, 0.0)

    lines = ["<b>Тикеры по биржам:</b>"]
    for ex, n in counts.items():
        emoji = "✅" if n > 0 else "❌"
        lines.append(f"{emoji} {ex}: {n}")
    lines.append("")
    lines.append(f"Сырых вилок ≥ {user.threshold}%: <b>{len(spreads_at)}</b>")
    lines.append(f"Всего пар с положительным спредом: <b>{len(spreads_top)}</b>")

    if spreads_top:
        lines.append("")
        lines.append("<b>Топ-5 сырых спредов:</b>")
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
        reply_markup=_main_keyboard(_is_admin(message)),
    )
