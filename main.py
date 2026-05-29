"""Точка входа: запускает Telegram-бот и фоновый цикл поиска вилок."""
import asyncio
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from loguru import logger

from config import (
    ADMIN_TELEGRAM_ID,
    POLL_INTERVAL_SECONDS,
    TELEGRAM_BOT_TOKEN,
)
from arbitrage.finder import find_spreads
from bot.handlers import router
from database.session import init_db
from database.users_repo import get_active_users
from exchanges.fetcher import fetch_all_tickers


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
    """Каждые N секунд опрашивает биржи и рассылает вилки активным юзерам."""
    logger.info("Фоновый цикл арбитража запущен")
    while True:
        try:
            tickers = await fetch_all_tickers()
            all_spreads = find_spreads(tickers, 0.0)
            users = await get_active_users()
            logger.info(
                f"Активных юзеров: {len(users)}, всего вилок: {len(all_spreads)}"
            )

            send_tasks = []
            for user in users:
                personal = [s for s in all_spreads if s.spread_percent >= user.threshold]
                for spread in personal[:10]:
                    send_tasks.append(
                        _send_signal_safe(bot, user.telegram_id, spread.format_message())
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

    asyncio.create_task(arbitrage_loop(bot))

    logger.info("Бот запущен. Жду команды в Telegram...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Остановка по Ctrl+C")
