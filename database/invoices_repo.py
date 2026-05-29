"""CRUD-операции для счетов CryptoBot."""
from datetime import datetime

from sqlalchemy import select, update

from database.models import Invoice
from database.session import async_session_factory


async def create_invoice(
    invoice_id: int,
    user_id: int,
    tier: str,
    days: int,
    amount_usd: float,
    pay_url: str,
) -> None:
    async with async_session_factory() as session:
        inv = Invoice(
            invoice_id=invoice_id,
            user_id=user_id,
            tier=tier,
            days=days,
            amount_usd=amount_usd,
            pay_url=pay_url,
            status="active",
        )
        session.add(inv)
        await session.commit()


async def get_pending_invoices() -> list[Invoice]:
    async with async_session_factory() as session:
        result = await session.execute(
            select(Invoice).where(Invoice.status == "active")
        )
        return list(result.scalars().all())


async def mark_paid(invoice_id: int) -> Invoice | None:
    async with async_session_factory() as session:
        inv = await session.get(Invoice, invoice_id)
        if inv is None or inv.status != "active":
            return inv
        inv.status = "paid"
        inv.paid_at = datetime.utcnow()
        await session.commit()
        await session.refresh(inv)
        return inv


async def mark_delivered(invoice_id: int) -> None:
    async with async_session_factory() as session:
        await session.execute(
            update(Invoice)
            .where(Invoice.invoice_id == invoice_id)
            .values(status="delivered")
        )
        await session.commit()


async def mark_expired(invoice_id: int) -> None:
    async with async_session_factory() as session:
        await session.execute(
            update(Invoice)
            .where(Invoice.invoice_id == invoice_id)
            .values(status="expired")
        )
        await session.commit()
