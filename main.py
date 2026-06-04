"""Точка входа: Telegram-бот + цикл поиска и верификации вилок."""
import asyncio
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from loguru import logger

from config import (
    ADMIN_TELEGRAM_ID,
    BINANCE_API_KEY, BINANCE_API_SECRET,
    BYBIT_API_KEY, BYBIT_API_SECRET,
    MAX_CANDIDATES_FOR_VERIFY,
    OKX_API_KEY, OKX_API_SECRET, OKX_PASSPHRASE,
    POLL_INTERVAL_SECONDS,
    TELEGRAM_BOT_TOKEN,
    TRADER_ENABLED,
)
from arbitrage.finder import find_spreads
from arbitrage.verifier import verify_spread
from bot.broadcast import router as broadcast_router
from bot.handlers import router
from database.session import init_db
from database.users_repo import get_active_users
from exchanges.currencies_cache import cache as currencies_cache
from exchanges.fetcher import fetch_all_tickers
from subscriptions.expiry_notifier import expiry_notifier_loop
from subscriptions.invoice_poller import invoice_poller_loop
from subscriptions.tiers import effective_tier, features


logger.remove()
logger.add(sys.stderr, level="INFO")


async def _send_safe(bot: Bot, user_id: int, text: str) -> None:
    try:
        await bot.send_message(
            chat_id=user_id,
            text=text,
            disable_web_page_preview=True,
        )
    except Exception as e:
        logger.warning(f"Не отправилось user_id={user_id}: {e}")


def _build_trader_configs() -> dict:
    configs = {}
    if BYBIT_API_KEY and BYBIT_API_SECRET:
        configs["bybit"] = {"api_key": BYBIT_API_KEY, "api_secret": BYBIT_API_SECRET}
    if BINANCE_API_KEY and BINANCE_API_SECRET:
        configs["binance"] = {"api_key": BINANCE_API_KEY, "api_secret": BINANCE_API_SECRET}
    if OKX_API_KEY and OKX_API_SECRET:
        configs["okx"] = {
            "api_key": OKX_API_KEY,
            "api_secret": OKX_API_SECRET,
            "passphrase": OKX_PASSPHRASE,
        }
    return configs


async def arbitrage_loop(bot: Bot) -> None:
    from trader.loop import get_trader
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

            # ── Авто-трейдер ──────────────────────────────────────────────────
            trader = get_trader()
            if trader and verified:
                async def _notify(text: str) -> None:
                    await _send_safe(bot, ADMIN_TELEGRAM_ID, text)

                await trader.process_spreads(verified, notify=_notify)

            # ── Рассылка сигналов подписчикам ─────────────────────────────────
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
                    send_tasks.append(_send_safe(bot, user.telegram_id, sig.format_message()))
            if send_tasks:
                await asyncio.gather(*send_tasks, return_exceptions=True)

        except Exception as e:
            logger.exception(f"Ошибка в цикле арбитража: {e}")

        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def funding_rate_loop(bot: Bot) -> None:
    """Раз в 8 часов проверяет ставки финансирования и уведомляет админа."""
    from trader.funding import scan_funding_rates, format_funding_report, FUNDING_GOOD_RATE_8H
    logger.info("Фоновый мониторинг funding rate запущен (интервал: 8ч)")
    while True:
        await asyncio.sleep(8 * 3600)
        try:
            opportunities = await scan_funding_rates()
            good = [o for o in opportunities if o.is_good()]
            if good:
                report = format_funding_report(opportunities)
                await _send_safe(bot, ADMIN_TELEGRAM_ID, report)
                logger.info(f"Funding rate: {len(good)} хороших возможностей, уведомление отправлено")
        except Exception as e:
            logger.warning(f"Ошибка мониторинга funding rate: {e}")


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
    dp.include_router(broadcast_router)
    dp.include_router(router)

    from bot.runtime import runtime
    me = await bot.get_me()
    runtime.bot_username = me.username or ""
    logger.info(f"Бот @{runtime.bot_username} готов")

    # ── Авто-трейдер ──────────────────────────────────────────────────────────
    trader_configs = _build_trader_configs()
    if trader_configs:
        from trader.accounts import TraderAccounts
        from trader.loop import AutoTrader, set_trader
        accounts = TraderAccounts(trader_configs)
        trader = AutoTrader(accounts)
        trader.set_enabled(TRADER_ENABLED)
        set_trader(trader)
        logger.info(
            f"Авто-трейдер {'включён' if TRADER_ENABLED else 'настроен (выключен)'}, "
            f"биржи: {list(trader_configs.keys())}"
        )
    else:
        logger.info("Авто-трейдер: API-ключи не заданы, торговля отключена")

    asyncio.create_task(arbitrage_loop(bot))
    asyncio.create_task(invoice_poller_loop(bot))
    asyncio.create_task(expiry_notifier_loop(bot))
    asyncio.create_task(funding_rate_loop(bot))

    logger.info("Бот запущен. Жду команды в Telegram...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Остановка по Ctrl+C")
