"""Минималистичный клиент CryptoBot Pay API.

Доки: https://help.crypt.bot/crypto-pay-api
"""
from typing import Any

import aiohttp
from loguru import logger

from config import CRYPTOBOT_API_TOKEN, CRYPTOBOT_BASE_URL


class CryptoBotError(Exception):
    pass


def _headers() -> dict:
    return {"Crypto-Pay-API-Token": CRYPTOBOT_API_TOKEN}


def is_configured() -> bool:
    return bool(CRYPTOBOT_API_TOKEN)


async def _call(method: str, params: dict | None = None) -> Any:
    if not is_configured():
        raise CryptoBotError("CRYPTOBOT_API_TOKEN не задан в .env")
    url = f"{CRYPTOBOT_BASE_URL}/{method}"
    async with aiohttp.ClientSession() as s:
        async with s.post(url, json=params or {}, headers=_headers(), timeout=20) as r:
            data = await r.json()
    if not data.get("ok"):
        err = data.get("error", {})
        raise CryptoBotError(f"{method} failed: {err}")
    return data["result"]


async def get_me() -> dict:
    return await _call("getMe")


async def create_invoice(
    amount_usd: float,
    description: str,
    payload: str,
    expires_in: int = 3600,
) -> dict:
    """Создать счёт. Возвращает invoice dict (invoice_id, pay_url, ...)."""
    return await _call("createInvoice", {
        "currency_type": "fiat",
        "fiat": "USD",
        "accepted_assets": "USDT",
        "amount": f"{amount_usd:.2f}",
        "description": description,
        "payload": payload,
        "expires_in": expires_in,
        "allow_comments": False,
        "allow_anonymous": False,
    })


async def get_invoices_by_ids(invoice_ids: list[int]) -> list[dict]:
    if not invoice_ids:
        return []
    ids_str = ",".join(str(i) for i in invoice_ids)
    result = await _call("getInvoices", {"invoice_ids": ids_str, "count": len(invoice_ids)})
    return result.get("items", [])
