"""Фоновая задача: проверяет статус активных счетов и выдаёт подписки за оплату."""
import asyncio
from datetime import datetime

from aiogram import Bot
from loguru import logger

from config import INVOICE_POLL_INTERVAL_SECONDS, REFERRAL_PERCENT
from database.invoices_repo import (
    get_pending_invoices,
    mark_delivered,
    mark_expired,
    mark_paid,
)
from database.users_repo import (
    add_referral_balance,
    get_user,
    grant_subscription,
)
from subscriptions.crypto_bot import get_invoices_by_ids, is_configured
from subscriptions.tiers import features


async def _deliver(
    bot: Bot,
    invoice_id: int,
    user_id: int,
    tier: str,
    days: int,
    amount_usd: float,
) -> None:
    user = await grant_subscription(user_id, tier, days)
    await mark_delivered(invoice_id)
    if user is None:
        logger.warning(f"Invoice {invoice_id}: user {user_id} not found")
        return
    feats = features(tier)
    expires_str = user.subscription_expires_at.strftime("%Y-%m-%d %H:%M UTC") if user.subscription_expires_at else "—"
    try:
        await bot.send_message(
            chat_id=user_id,
            text=(
                f"🎉 <b>Оплата получена!</b>\n\n"
                f"Тариф: <b>{feats.name}</b>\n"
                f"Активен до: {expires_str}\n\n"
                f"Спасибо! Сигналы по новому тарифу пойдут в следующем цикле."
            ),
        )
    except Exception as e:
        logger.warning(f"Не отправилось пользователю {user_id}: {e}")

    if user.referrer_id:
        commission = amount_usd * REFERRAL_PERCENT / 100
        await add_referral_balance(user.referrer_id, commission)
        try:
            await bot.send_message(
                chat_id=user.referrer_id,
                text=(
                    f"💸 <b>Реферальное начисление</b>\n\n"
                    f"Твой реферал оплатил подписку — начислено "
                    f"<b>{commission:.2f} USDT</b> ({REFERRAL_PERCENT}%).\n\n"
                    f"Посмотреть баланс: 🔗 Реферальная система."
                ),
            )
        except Exception as e:
            logger.warning(f"Не отправилось рефереру {user.referrer_id}: {e}")


async def invoice_poller_loop(bot: Bot) -> None:
    if not is_configured():
        logger.warning("CRYPTOBOT_API_TOKEN не задан — invoice poller выключен")
        return
    logger.info("Фоновый цикл проверки счетов запущен")
    while True:
        try:
            pending = await get_pending_invoices()
            if pending:
                ids = [inv.invoice_id for inv in pending]
                remote = await get_invoices_by_ids(ids)
                remote_by_id = {item["invoice_id"]: item for item in remote}
                for inv in pending:
                    r = remote_by_id.get(inv.invoice_id)
                    if r is None:
                        continue
                    status = r.get("status")
                    if status == "paid":
                        marked = await mark_paid(inv.invoice_id)
                        if marked is not None:
                            await _deliver(
                                bot, inv.invoice_id, inv.user_id,
                                inv.tier, inv.days, inv.amount_usd,
                            )
                    elif status == "expired":
                        await mark_expired(inv.invoice_id)
        except Exception as e:
            logger.exception(f"Ошибка в invoice_poller: {e}")
        await asyncio.sleep(INVOICE_POLL_INTERVAL_SECONDS)
