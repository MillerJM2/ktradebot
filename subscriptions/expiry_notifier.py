"""Фоновая задача: уведомления об истечении подписки и пробного периода."""
import asyncio
from datetime import datetime, timezone

from aiogram import Bot
from loguru import logger

from config import EXPIRY_CHECK_INTERVAL_SECONDS
from database.users_repo import (
    get_users_with_active_subscription,
    set_reminder_milestone,
)
from subscriptions.tiers import features


PAID_MILESTONES = [
    (7, "📅 До окончания подписки осталось <b>7 дней</b>.\nПродли заранее в разделе <b>💎 Тарифы</b>."),
    (3, "⏰ До окончания подписки осталось <b>3 дня</b>.\nНе забудь продлить — раздел <b>💎 Тарифы</b>."),
    (1, "⚠️ <b>До окончания подписки 1 день!</b>\nПродли подписку, чтобы не потерять доступ — <b>💎 Тарифы</b>."),
    (0, "❌ <b>Твоя подписка истекла.</b>\nДоступ к сигналам приостановлен. Продлить можно в разделе <b>💎 Тарифы</b>."),
]

TRIAL_MILESTONES = [
    (1, (
        "⏰ <b>Пробный доступ заканчивается завтра!</b>\n\n"
        "За эти дни ты получал реальные проверенные вилки — сигналы которые проходят "
        "через 4 фильтра: вывод открыт, депозит открыт, общая сеть, реальный стакан.\n\n"
        "Чтобы не терять поток сигналов, оформи подписку: <b>💎 Тарифы</b>"
    )),
    (0, (
        "❌ <b>Пробный период завершён.</b>\n\n"
        "Надеемся, ты успел оценить качество сигналов!\n\n"
        "Подписка открывает:\n"
        "▪️ Неограниченный поток сигналов\n"
        "▪️ Более низкий порог спреда\n"
        "▪️ Пары к BTC и USDT\n\n"
        "Оформить: <b>💎 Тарифы</b>"
    )),
]


async def _notify(bot: Bot, user_id: int, text: str) -> None:
    try:
        await bot.send_message(chat_id=user_id, text=text)
    except Exception as e:
        logger.warning(f"expiry notify failed user={user_id}: {e}")


async def expiry_notifier_loop(bot: Bot) -> None:
    logger.info("Фоновый цикл уведомлений об истечении запущен")
    while True:
        try:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            users = await get_users_with_active_subscription()
            for user in users:
                if user.subscription_expires_at is None:
                    continue
                feats = features(user.tier)
                if feats.is_lifetime:
                    continue

                expires = user.subscription_expires_at.replace(tzinfo=None)
                days_left = (expires - now).total_seconds() / 86400
                last = user.reminder_milestone if user.reminder_milestone is not None else 999

                milestones = TRIAL_MILESTONES if user.tier == "trial" else PAID_MILESTONES
                for threshold, text in milestones:
                    if days_left <= threshold and last > threshold:
                        await _notify(bot, user.telegram_id, text)
                        await set_reminder_milestone(user.telegram_id, threshold)
                        break
        except Exception as e:
            logger.exception(f"expiry_notifier error: {e}")
        await asyncio.sleep(EXPIRY_CHECK_INTERVAL_SECONDS)
