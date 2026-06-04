"""CRUD-операции для таблицы сделок авто-трейдера."""
from datetime import datetime, timezone

from sqlalchemy import func, select

from database.models import Trade
from database.session import async_session_factory


async def create_trade(
    symbol: str,
    buy_exchange: str,
    sell_exchange: str,
    amount_usdt: float,
    buy_price: float,
    sell_price: float,
    amount_coin: float,
    gross_profit_usd: float,
    trade_fees_usd: float,
    net_profit_usd: float,
    status: str = "completed",
    error_msg: str | None = None,
) -> Trade:
    async with async_session_factory() as session:
        trade = Trade(
            symbol=symbol,
            buy_exchange=buy_exchange,
            sell_exchange=sell_exchange,
            amount_usdt=amount_usdt,
            buy_price=buy_price,
            sell_price=sell_price,
            amount_coin=amount_coin,
            gross_profit_usd=gross_profit_usd,
            trade_fees_usd=trade_fees_usd,
            net_profit_usd=net_profit_usd,
            status=status,
            error_msg=error_msg,
            executed_at=datetime.now(timezone.utc),
        )
        session.add(trade)
        await session.commit()
        await session.refresh(trade)
        return trade


async def get_recent_trades(limit: int = 20) -> list[Trade]:
    async with async_session_factory() as session:
        result = await session.execute(
            select(Trade).order_by(Trade.executed_at.desc()).limit(limit)
        )
        return list(result.scalars().all())


async def get_daily_stats() -> dict:
    """Статистика за текущий день (UTC)."""
    today = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    async with async_session_factory() as session:
        result = await session.execute(
            select(
                func.count(Trade.id).label("cnt"),
                func.coalesce(func.sum(Trade.net_profit_usd), 0.0).label("profit"),
            ).where(
                Trade.executed_at >= today,
                Trade.status == "completed",
            )
        )
        row = result.one()
        profit = float(row.profit)
        return {
            "trade_count": int(row.cnt),
            "net_profit": profit,
        }


async def get_all_time_stats() -> dict:
    async with async_session_factory() as session:
        result = await session.execute(
            select(
                func.count(Trade.id).label("cnt"),
                func.coalesce(func.sum(Trade.net_profit_usd), 0.0).label("profit"),
            ).where(Trade.status == "completed")
        )
        row = result.one()
        return {
            "trade_count": int(row.cnt),
            "net_profit": float(row.profit),
        }
