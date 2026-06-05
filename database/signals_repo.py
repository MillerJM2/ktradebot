"""CRUD для логов сигналов и агрегатных запросов для /stats."""
from datetime import datetime, timedelta

from sqlalchemy import delete, desc, func, select

from database.models import SignalLog
from database.session import async_session_factory


async def log_signal(spread) -> None:
    """spread: VerifiedSpread из arbitrage.verifier"""
    async with async_session_factory() as session:
        session.add(SignalLog(
            timestamp=datetime.utcnow(),
            symbol=spread.symbol,
            buy_exchange=spread.buy_exchange,
            sell_exchange=spread.sell_exchange,
            net_profit_percent=spread.net_profit_percent,
            raw_spread_percent=spread.raw_spread_percent,
            buy_volume_usd=spread.buy_volume_usd,
            sell_volume_usd=spread.sell_volume_usd,
            network=spread.network,
            withdraw_fee_usd=spread.withdraw_fee_usd,
            target_amount_usd=spread.target_amount_usd,
        ))
        await session.commit()


async def count_signals_since(since: datetime) -> int:
    async with async_session_factory() as session:
        result = await session.execute(
            select(func.count(SignalLog.id)).where(SignalLog.timestamp >= since)
        )
        return int(result.scalar() or 0)


async def stats_aggregate(since: datetime) -> dict:
    async with async_session_factory() as session:
        total_q = select(
            func.count(SignalLog.id),
            func.avg(SignalLog.net_profit_percent),
            func.max(SignalLog.net_profit_percent),
            func.count(func.distinct(SignalLog.symbol)),
        ).where(SignalLog.timestamp >= since)
        row = (await session.execute(total_q)).one()
        return {
            "total": int(row[0] or 0),
            "avg_profit": float(row[1] or 0.0),
            "max_profit": float(row[2] or 0.0),
            "unique_symbols": int(row[3] or 0),
        }


async def top_symbols(since: datetime, limit: int = 5) -> list[tuple[str, int]]:
    async with async_session_factory() as session:
        q = (
            select(SignalLog.symbol, func.count(SignalLog.id).label("c"))
            .where(SignalLog.timestamp >= since)
            .group_by(SignalLog.symbol)
            .order_by(desc("c"))
            .limit(limit)
        )
        rows = (await session.execute(q)).all()
        return [(r[0], int(r[1])) for r in rows]


async def top_routes(since: datetime, limit: int = 5) -> list[tuple[str, str, int]]:
    async with async_session_factory() as session:
        q = (
            select(
                SignalLog.buy_exchange,
                SignalLog.sell_exchange,
                func.count(SignalLog.id).label("c"),
            )
            .where(SignalLog.timestamp >= since)
            .group_by(SignalLog.buy_exchange, SignalLog.sell_exchange)
            .order_by(desc("c"))
            .limit(limit)
        )
        rows = (await session.execute(q)).all()
        return [(r[0], r[1], int(r[2])) for r in rows]


async def cleanup_old(days: int = 90) -> int:
    """Удалить логи старше N дней. Возвращает кол-во удалённых."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    async with async_session_factory() as session:
        result = await session.execute(
            delete(SignalLog).where(SignalLog.timestamp < cutoff)
        )
        await session.commit()
        return result.rowcount or 0
