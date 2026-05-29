"""Точка входа: Telegram-бот + цикл поиска и верификации вилок."""
import asyncio
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from loguru import logger

from config import (
    ADMIN_TELEGRAM_ID,
    MAX_CANDIDATES_FOR_VERIFY,
    POLL_INTERVAL_SECONDS,
    TELEGRAM_BOT_TOKEN,
)
from arbitrage.finder import find_spreads
from arbitrage.verifier import verify_spread
from bot.handlers import router
from database.session import init_db
from database.users_repo import get_active_users
from exchanges.currencies_cache import cache as currencies_cache
from exchanges.fetcher import fetch_all_tickers
from subscriptions.invoice_poller import invoice_poller_loop
from subscriptions.tiers import effective_tier, features


logger.remove()
logger.add(sys.stderr, level="INFO")


async def _send_signal_safe(bot: Bot, user_id: int, text: str) -> None:
    try:
        await bot.send_message(
            chat_id=user_id,
            text=text,
            disable_web_page_preview=True,
        )
    except Exception as e:
        logger.warning(f"Не отправилось user_id={user_id}: {e}")


async def arbitrage_loop(bot: Bot) -> None:
    logger.info("Фоновый цикл арбитража запущен")
    while True:
        try:
            await currencies_cache.refresh_if_needed()

            tickers = await fetch_all_tickers()
            raw_spreads = find_spreads(tickers, 0.5)
            logger.info(f"Сырых кандидатов: {len(raw_spreads)}")

            verify_tasks = [
                verify_spread(
                    s.symbol,
                    s.buy_exchange, s.buy_volume_usd,
                    s.sell_exchange, s.sell_volume_usd,
                )
                for s in raw_spreads[:MAX_CANDIDATES_FOR_VERIFY]
            ]
            verified = [
                v for v in await asyncio.gather(*verify_tasks, return_exceptions=False)
                if v is not None
            ]
            verified.sort(key=lambda v: v.net_profit_percent, reverse=True)
            logger.info(f"Прошли все фильтры: {len(verified)}")

            users = await get_active_users()
            send_tasks = []
            for user in users:
                tier = effective_tier(user.tier, user.subscription_expires_at)
                feats = features(tier)
                if feats.max_signals_per_cycle == 0:
                    continue
                user_threshold = max(user.threshold, feats.min_threshold)
                personal = [
                    v for v in verified
                    if v.net_profit_percent >= user_threshold
                    and v.buy_exchange in feats.allowed_exchanges
                    and v.sell_exchange in feats.allowed_exchanges
                    and v.symbol.split("/", 1)[1] in feats.quote_currencies
                ]
                for sig in personal[:feats.max_signals_per_cycle]:
                    send_tasks.append(
                        _send_signal_safe(bot, user.telegram_id, sig.format_message())
                    )
            if send_tasks:
                await asyncio.gather(*send_tasks, return_exceptions=True)
        except Exception as e:
            logger.exception(f"Ошибка в цикле арбитража: {e}")

        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def main() -> None:
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN.startswith("сюда"):
        logger.error("TELEGRAM_BOT_TOKEN не задан в .env")
        sys.exit(1)
    if not ADMIN_TELEGRAM_ID:
        logger.error("ADMIN_TELEGRAM_ID не задан в .env")
        sys.exit(1)

    logger.info("Инициализация БД...")
    await init_db()

    bot = Bot(
        token=TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(router)

    from bot.runtime import runtime
    me = await bot.get_me()
    runtime.bot_username = me.username or ""
    logger.info(f"Бот @{runtime.bot_username} готов")

    asyncio.create_task(arbitrage_loop(bot))
    asyncio.create_task(invoice_poller_loop(bot))

    logger.info("Бот запущен. Жду команды в Telegram...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Остановка по Ctrl+C")
