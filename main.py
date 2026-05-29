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
from exchanges.fetcher import fetch_all_tickers
from arbitrage.finder import find_spreads
from bot.handlers import router, state


logger.remove()
logger.add(sys.stderr, level="INFO")


async def arbitrage_loop(bot: Bot) -> None:
    """Фоновая задача: каждые N секунд опрашивает биржи и шлёт сигналы админу."""
    logger.info("Фоновый цикл арбитража запущен")
    while True:
        try:
            if state.paused:
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                continue

            tickers = await fetch_all_tickers()
            spreads = find_spreads(tickers, state.threshold)

            logger.info(f"Найдено вилок: {len(spreads)} (порог {state.threshold}%)")

            for spread in spreads[:10]:
                try:
                    await bot.send_message(
                        chat_id=ADMIN_TELEGRAM_ID,
                        text=spread.format_message(),
                    )
                except Exception as e:
                    logger.warning(f"Не удалось отправить сообщение: {e}")
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
