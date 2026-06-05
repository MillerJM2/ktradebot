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

import uuid
from datetime import datetime, timedelta

from config import (
    ADMIN_TELEGRAM_ID,
    CHANNEL_NAME,
    CHANNEL_URL,
    MIN_WITHDRAW_USD,
    PROMO_UNTIL_DATE,
    PROMO_VISIBLE_TO_USERS,
    REFERRAL_PERCENT,
)
from bot.runtime import runtime
from database.invoices_repo import create_invoice as save_invoice
from database.users_repo import (
    count_referrals,
    count_users,
    find_user_by_username,
    get_or_create_user,
    grant_subscription,
    list_users,
    restore_referral_balance,
    revoke_subscription,
    set_paused,
    set_referrer,
    set_threshold,
    withdraw_referral_balance,
)
from subscriptions.crypto_bot import (
    CryptoBotError,
    create_invoice,
    is_configured as cryptobot_configured,
    transfer_usdt,
)
from arbitrage.exchange_info import display_name as exchange_display_name
from database.signals_repo import (
    stats_aggregate,
    top_routes,
    top_symbols,
)
from subscriptions.tiers import PAID_TIERS, TIERS, effective_tier, features


router = Router()


BTN_CABINET = "👤 Личный кабинет"
BTN_CHANNEL = "📺 Наш канал"
BTN_ABOUT = "ℹ️ О боте"
BTN_TARIFFS = "💎 Тарифы"
BTN_REFERRAL = "🔗 Реферальная система"
BTN_SUPPORT = "💼 Техническая поддержка"
BTN_DIAG = "🔍 Диагностика"
BTN_STATS = "📈 Статистика"
BTN_BROADCAST = "📢 Рассылка"

BTN_STATUS = "📊 Статус"
BTN_THRESHOLD = "🎯 Порог спреда"
BTN_PAUSE = "⏸ Пауза"
BTN_RESUME = "▶️ Запустить"
BTN_BACK = "🔙 В главное меню"


def _main_keyboard(is_admin: bool) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=BTN_CABINET)],
        [KeyboardButton(text=BTN_TARIFFS)],
        [KeyboardButton(text=BTN_CHANNEL)],
        [KeyboardButton(text=BTN_ABOUT)],
        [KeyboardButton(text=BTN_REFERRAL)],
        [KeyboardButton(text=BTN_SUPPORT)],
    ]
    if is_admin:
        rows.append([KeyboardButton(text=BTN_DIAG), KeyboardButton(text=BTN_STATS)])
        rows.append([KeyboardButton(text=BTN_BROADCAST)])
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


def _no_sub_text() -> str:
    return (
        "🔒 <b>Доступ к инструменту заблокирован</b>\n\n"
        "Подписка: ❌\n\n"
        "Обратитесь: <i>скоро будет ссылка</i>, для получения доступа."
    )


def _parse_referrer_from_start(text: str | None) -> int | None:
    if not text:
        return None
    parts = text.split(maxsplit=1)
    if len(parts) < 2:
        return None
    payload = parts[1].strip()
    if not payload.startswith("ref_"):
        return None
    try:
        return int(payload[4:])
    except ValueError:
        return None


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    referrer_id = _parse_referrer_from_start(message.text)
    user = await get_or_create_user(
        message.from_user.id, message.from_user.username
    )
    if referrer_id is not None and user.referrer_id is None:
        await set_referrer(message.from_user.id, referrer_id)
    is_admin = _is_admin(message)
    tier_eff = effective_tier(user.tier, user.subscription_expires_at)
    feats = features(tier_eff)
    has_sub = tier_eff in PAID_TIERS or tier_eff == "admin"
    if has_sub:
        body = (
            f"Твой тариф: <b>{feats.name}</b>\n"
            f"Доступно бирж: {len(feats.allowed_exchanges)}\n"
            f"Минимальный порог: {feats.min_threshold}%"
        )
        text = f"👋 <b>Добро пожаловать в KTradeClub</b>\n\n{body}"
    else:
        text = (
            f"👋 <b>Добро пожаловать в KTradeClub</b>\n\n"
            f"{_no_sub_text()}"
        )
    await message.answer(text, reply_markup=_main_keyboard(is_admin))


@router.message(F.text == BTN_CABINET)
async def btn_cabinet(message: Message) -> None:
    user = await get_or_create_user(
        message.from_user.id, message.from_user.username
    )
    tier_eff = effective_tier(user.tier, user.subscription_expires_at)
    feats = features(tier_eff)
    has_sub = tier_eff in PAID_TIERS or tier_eff == "admin"
    if not has_sub:
        await message.answer(
            _no_sub_text(),
            reply_markup=_main_keyboard(_is_admin(message)),
        )
        return
    paused_str = "на паузе ⏸" if user.paused else "активен ✅"
    sub_line = (
        f"Тариф: <b>{feats.name}</b> до "
        f"{_format_expiry(user.subscription_expires_at)}"
    )
    await message.answer(
        f"👤 <b>Личный кабинет</b>\n\n"
        f"{sub_line}\n"
        f"Состояние: {paused_str}\n"
        f"Порог: {user.threshold}%",
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
    has_sub = tier_eff in PAID_TIERS or tier_eff == "admin"
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
        text = _no_sub_text()
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
        "Бот отслеживает цены криптовалют на 10 крупнейших CEX биржах и присылает "
        "уведомления о <b>проверенных</b> межбиржевых вилках.\n\n"
        "Каждый сигнал проходит 4 фильтра:\n"
        "1. Вывод включён на бирже покупки\n"
        "2. Депозит включён на бирже продажи\n"
        "3. Есть общая работающая сеть\n"
        "4. Реальный спред по стакану + после комиссий ≥ порог\n\n"
        f"📺 Новости и обзоры — в нашем канале: {CHANNEL_URL}",
        reply_markup=_main_keyboard(_is_admin(message)),
    )


@router.message(F.text == BTN_CHANNEL)
async def btn_channel(message: Message) -> None:
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"📺 Перейти в {CHANNEL_NAME}", url=CHANNEL_URL)],
    ])
    await message.answer(
        f"📺 <b>{CHANNEL_NAME}</b>\n\n"
        f"Новости, обзоры арбитража, разборы кейсов.\n"
        f"Подпишись, чтобы не пропустить — там много полезного.",
        reply_markup=kb,
    )


def _tariff_card_text(tier_key: str) -> str:
    t = features(tier_key)
    bullets = "\n".join(f"▪️ {b}" for b in t.bullets)
    return (
        f"<b>Тариф {t.name}</b>\n\n"
        f"{bullets}\n\n"
        f"Акция до {PROMO_UNTIL_DATE}\n\n"
        f"Старая цена: <s>{t.old_price_usd:g} USDT</s>\n"
        f"Новая цена: <b>{t.price_usd:g} USDT</b>"
    )


def _buy_button(tier_key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Приобрести", callback_data=f"buy:{tier_key}")],
    ])


@router.message(F.text == BTN_TARIFFS)
async def btn_tariffs(message: Message) -> None:
    user = await get_or_create_user(
        message.from_user.id, message.from_user.username
    )
    tier_eff = effective_tier(user.tier, user.subscription_expires_at)
    if tier_eff in ("admin",):
        header = f"💎 <b>Тарифы</b>\n\nТвой текущий: <b>{features(tier_eff).name}</b>"
    elif tier_eff in PAID_TIERS:
        header = (
            f"💎 <b>Тарифы</b>\n\n"
            f"Твой текущий: <b>{features(tier_eff).name}</b>\n"
            f"Действует до: {_format_expiry(user.subscription_expires_at)}"
        )
    else:
        header = "💎 <b>Тарифы</b>\n\nУ тебя пока <b>нет активной подписки</b>."
    if PROMO_VISIBLE_TO_USERS and user.pending_promo_code:
        header += f"\n\n🎟️ Применится промокод: <code>{user.pending_promo_code}</code>"
    await message.answer(
        header,
        reply_markup=_main_keyboard(_is_admin(message)),
    )
    if PROMO_VISIBLE_TO_USERS:
        promo_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎟️ У меня есть промокод", callback_data="promo_enter")],
        ])
        await message.answer("Если у тебя есть промокод — введи его:", reply_markup=promo_kb)
    for tier_key in PAID_TIERS:
        await message.answer(
            _tariff_card_text(tier_key),
            reply_markup=_buy_button(tier_key),
        )


@router.callback_query(F.data.startswith("buy:"))
async def cb_buy(callback: CallbackQuery) -> None:
    await callback.answer()
    tier = callback.data.split(":", 1)[1]
    if tier not in PAID_TIERS:
        await callback.message.answer("❌ Неизвестный тариф.")
        return
    feats = features(tier)
    user = await get_or_create_user(
        callback.from_user.id, callback.from_user.username
    )
    if not cryptobot_configured():
        await callback.message.answer(
            "⏳ Оплата картой/криптой скоро будет доступна. Пока обратитесь по контакту из поддержки."
        )
        return

    final_price = feats.price_usd
    applied_promo: str | None = None
    discount_percent = 0.0

    if user.pending_promo_code:
        from database.promo_repo import (
            get_promo as _get_promo,
            has_user_used as _has_used,
            record_usage as _record_usage,
            set_user_pending_promo as _set_pending,
            validate as _validate,
        )
        promo = await _get_promo(user.pending_promo_code)
        err = _validate(promo)
        if err or promo.type != "discount" or await _has_used(promo.code, user.telegram_id):
            await _set_pending(user.telegram_id, None)
        else:
            discount_percent = promo.value
            final_price = round(feats.price_usd * (1 - discount_percent / 100), 2)
            applied_promo = promo.code
            await _record_usage(promo.code, user.telegram_id, tier, discount_percent)
            await _set_pending(user.telegram_id, None)

    try:
        invoice = await create_invoice(
            amount_usd=final_price,
            description=f"Подписка {feats.name} ({feats.duration_days} дней)",
            payload=f"{user.telegram_id}:{tier}:{feats.duration_days}",
        )
    except CryptoBotError as e:
        logger.warning(f"createInvoice failed: {e}")
        await callback.message.answer(
            "❌ Не удалось создать счёт. Попробуй позже."
        )
        return
    await save_invoice(
        invoice_id=int(invoice["invoice_id"]),
        user_id=user.telegram_id,
        tier=tier,
        days=feats.duration_days,
        amount_usd=final_price,
        pay_url=invoice["pay_url"],
    )
    pay_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Перейти к оплате", url=invoice["pay_url"])],
    ])
    duration_str = "пожизненно" if feats.is_lifetime else f"{feats.duration_days} дней"
    promo_line = (
        f"\n🎟️ Промокод <code>{applied_promo}</code>: -{discount_percent:g}%"
        if applied_promo else ""
    )
    await callback.message.answer(
        f"💳 <b>Счёт создан</b>\n\n"
        f"Тариф: <b>{feats.name}</b>\n"
        f"Сумма: <b>{final_price:g} USDT</b>{promo_line}\n"
        f"Срок: {duration_str}\n\n"
        f"Жми кнопку — оплата в @CryptoBot. После оплаты подписка активируется автоматически в течение минуты.",
        reply_markup=pay_kb,
    )


@router.message(F.text == BTN_REFERRAL)
async def btn_referral(message: Message) -> None:
    user = await get_or_create_user(
        message.from_user.id, message.from_user.username
    )
    invited = await count_referrals(message.from_user.id)
    bot_un = runtime.bot_username or "your_bot"
    ref_link = f"https://t.me/{bot_un}?start=ref_{message.from_user.id}"
    balance = user.referral_balance_usd or 0.0
    total_earned = user.total_referral_earned_usd or 0.0

    withdraw_kb = None
    if balance >= MIN_WITHDRAW_USD and cryptobot_configured():
        withdraw_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text=f"💸 Вывести {balance:.2f} USDT",
                callback_data="ref_withdraw",
            )],
        ])
    withdraw_note = (
        f"Минимум для вывода: <b>{MIN_WITHDRAW_USD:g} USDT</b>"
        if balance < MIN_WITHDRAW_USD else
        "Вывод происходит мгновенно через @CryptoBot"
    )

    await message.answer(
        f"🔗 <b>Реферальная система</b>\n\n"
        f"Приглашай друзей и получай <b>{REFERRAL_PERCENT}% от их подписок</b> "
        f"на свой баланс.\n\n"
        f"Твоя ссылка:\n"
        f"<code>{ref_link}</code>\n\n"
        f"📊 Приглашено: <b>{invited}</b>\n"
        f"💰 Всего заработано: <b>{total_earned:.2f} USDT</b>\n"
        f"🏦 Текущий баланс: <b>{balance:.2f} USDT</b>\n\n"
        f"{withdraw_note}",
        reply_markup=_main_keyboard(_is_admin(message)),
    )
    if withdraw_kb is not None:
        await message.answer("Вывод средств:", reply_markup=withdraw_kb)


@router.callback_query(F.data == "ref_withdraw")
async def cb_withdraw(callback: CallbackQuery) -> None:
    await callback.answer()
    user = await get_or_create_user(
        callback.from_user.id, callback.from_user.username
    )
    if not cryptobot_configured():
        await callback.message.answer("⏳ Оплата временно недоступна.")
        return
    if (user.referral_balance_usd or 0.0) < MIN_WITHDRAW_USD:
        await callback.message.answer(
            f"❌ Минимальная сумма вывода — {MIN_WITHDRAW_USD:g} USDT."
        )
        return

    amount = await withdraw_referral_balance(user.telegram_id)
    if amount < MIN_WITHDRAW_USD:
        await restore_referral_balance(user.telegram_id, amount)
        await callback.message.answer("❌ Недостаточно средств для вывода.")
        return

    spend_id = f"ref-{user.telegram_id}-{uuid.uuid4().hex[:16]}"
    try:
        await transfer_usdt(
            user_id=user.telegram_id,
            amount_usd=amount,
            spend_id=spend_id,
            comment=f"KTradeClub referral payout {amount:.2f} USDT",
        )
    except CryptoBotError as e:
        await restore_referral_balance(user.telegram_id, amount)
        logger.warning(f"Transfer failed: {e}")
        await callback.message.answer(
            "❌ Не удалось отправить перевод.\n\n"
            "Возможные причины:\n"
            "• Ты ни разу не открывал @CryptoBot (открой и нажми /start)\n"
            "• Временная проблема CryptoBot\n\n"
            "Баланс возвращён. Попробуй ещё раз."
        )
        return
    await callback.message.answer(
        f"✅ <b>{amount:.2f} USDT</b> отправлены тебе в @CryptoBot."
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
            "Тарифы: base, standart, pro, premium, free\n"
            "Пример: <code>/grant @ivanov pro 365</code>"
        )
        return
    target, tier, days_str = parts[1], parts[2], parts[3]
    if tier not in ("free", *PAID_TIERS):
        await message.answer("❌ Тариф должен быть: base, standart, pro, premium, free")
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


def _parse_period(text: str | None) -> tuple[timedelta, str]:
    """Парсит '/stats 7d', '/stats 24h' и т.п. Возвращает (delta, человекочитаемая_строка)."""
    parts = (text or "").split()
    arg = parts[1].lower() if len(parts) > 1 else "24h"
    if arg.endswith("d") and arg[:-1].isdigit():
        days = int(arg[:-1])
        return timedelta(days=days), f"{days} дн."
    if arg.endswith("h") and arg[:-1].isdigit():
        hours = int(arg[:-1])
        return timedelta(hours=hours), f"{hours} ч."
    return timedelta(hours=24), "24 ч."


@router.message(Command("stats"))
@router.message(F.text == BTN_STATS)
async def cmd_stats(message: Message) -> None:
    if not _is_admin(message):
        return
    delta, period_str = _parse_period(message.text)
    since = datetime.utcnow() - delta

    agg = await stats_aggregate(since)
    pairs = await top_symbols(since, limit=5)
    routes = await top_routes(since, limit=5)
    users_total = await count_users()

    if agg["total"] == 0:
        await message.answer(
            f"📈 <b>Статистика за {period_str}</b>\n\n"
            f"Сигналов пока нет. Попробуй позже или выбери больший период: "
            f"<code>/stats 7d</code>."
        )
        return

    lines = [
        f"📈 <b>Статистика за {period_str}</b>",
        "",
        f"Сигналов: <b>{agg['total']}</b>",
        f"Уникальных пар: <b>{agg['unique_symbols']}</b>",
        f"Средний чистый спред: <b>{agg['avg_profit']:.2f}%</b>",
        f"Максимальный: <b>{agg['max_profit']:.2f}%</b>",
        "",
        "<b>🏆 Топ-5 пар:</b>",
    ]
    for sym, cnt in pairs:
        lines.append(f"• {sym} — {cnt}")
    lines.append("")
    lines.append("<b>🔄 Топ-5 маршрутов:</b>")
    for buy, sell, cnt in routes:
        lines.append(
            f"• {exchange_display_name(buy)} → {exchange_display_name(sell)} — {cnt}"
        )
    lines.append("")
    lines.append(f"👥 Всего пользователей в БД: <b>{users_total}</b>")

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
