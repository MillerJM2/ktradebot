"""Кэш статусов вывода/депозита и поддерживаемых сетей для каждой монеты.

Обновляется в фоне раз в CURRENCIES_REFRESH_SECONDS — нельзя запрашивать
fetch_currencies() при каждом сигнале, словим rate-limit.
"""
import asyncio
import time

import ccxt.async_support as ccxt
from loguru import logger

from config import CURRENCIES_REFRESH_SECONDS, EXCHANGES, REQUEST_TIMEOUT


NETWORK_ALIASES = {
    "ERC20": "ETH",
    "ETHEREUM": "ETH",
    "BEP20": "BSC",
    "BNB SMART CHAIN": "BSC",
    "BSC(BEP20)": "BSC",
    "TRC20": "TRX",
    "TRON": "TRX",
    "MATIC": "POLYGON",
    "POL": "POLYGON",
    "ARB": "ARBITRUM",
    "ARBITRUMONE": "ARBITRUM",
    "OP": "OPTIMISM",
}


def _normalize_network(name: str) -> str:
    if not name:
        return ""
    up = name.upper().replace(" ", "").replace("-", "").replace("_", "")
    return NETWORK_ALIASES.get(up, up)


class CurrenciesCache:
    def __init__(self) -> None:
        # {exchange: {coin: {"networks": {net: {withdraw, deposit, fee}}}}}
        self._data: dict[str, dict[str, dict]] = {}
        self._last_refresh_ts: float = 0.0
        self._lock = asyncio.Lock()

    def is_loaded(self) -> bool:
        return bool(self._data)

    async def refresh_if_needed(self) -> None:
        if time.time() - self._last_refresh_ts < CURRENCIES_REFRESH_SECONDS and self._data:
            return
        async with self._lock:
            if time.time() - self._last_refresh_ts < CURRENCIES_REFRESH_SECONDS and self._data:
                return
            await self._refresh()

    async def _refresh(self) -> None:
        logger.info("Обновляю кэш валют со всех бирж...")
        tasks = [self._fetch_one(name) for name in EXCHANGES]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        new_data: dict[str, dict[str, dict]] = {}
        for name, result in zip(EXCHANGES, results):
            if isinstance(result, Exception):
                logger.warning(f"[{name}] currencies error: {result}")
                if name in self._data:
                    new_data[name] = self._data[name]
                continue
            new_data[name] = result
        self._data = new_data
        self._last_refresh_ts = time.time()
        total = sum(len(v) for v in new_data.values())
        logger.info(f"Кэш валют обновлён: {total} (биржа × монета) записей")

    async def _fetch_one(self, name: str) -> dict[str, dict]:
        exchange_class = getattr(ccxt, name)
        exchange = exchange_class({
            "enableRateLimit": True,
            "timeout": REQUEST_TIMEOUT,
            "options": {"defaultType": "spot"},
        })
        try:
            currencies = await exchange.fetch_currencies() or {}
            result: dict[str, dict] = {}
            for code, info in currencies.items():
                networks_raw = info.get("networks") or {}
                networks: dict[str, dict] = {}
                for net_name, net_info in networks_raw.items():
                    norm = _normalize_network(net_name)
                    if not norm:
                        continue
                    networks[norm] = {
                        "withdraw": bool(net_info.get("withdraw")),
                        "deposit": bool(net_info.get("deposit")),
                        "fee": float(net_info.get("fee") or 0),
                    }
                result[code.upper()] = {
                    "top_withdraw": bool(info.get("withdraw")),
                    "top_deposit": bool(info.get("deposit")),
                    "networks": networks,
                }
            return result
        finally:
            await exchange.close()

    def _coin_info(self, exchange: str, coin: str) -> dict | None:
        return self._data.get(exchange, {}).get(coin.upper())

    def can_withdraw(self, exchange: str, coin: str) -> bool:
        info = self._coin_info(exchange, coin)
        if info is None:
            return False
        if any(n["withdraw"] for n in info["networks"].values()):
            return True
        return bool(info["top_withdraw"])

    def can_deposit(self, exchange: str, coin: str) -> bool:
        info = self._coin_info(exchange, coin)
        if info is None:
            return False
        if any(n["deposit"] for n in info["networks"].values()):
            return True
        return bool(info["top_deposit"])

    def find_common_network(
        self, buy_exchange: str, sell_exchange: str, coin: str
    ) -> tuple[str, float] | None:
        """Возвращает (имя сети, fee_в_монете) с минимальной комиссией. None если нет общей рабочей сети."""
        buy_info = self._coin_info(buy_exchange, coin)
        sell_info = self._coin_info(sell_exchange, coin)
        if buy_info is None or sell_info is None:
            return None
        buy_nets = buy_info["networks"]
        sell_nets = sell_info["networks"]

        candidates: list[tuple[str, float]] = []
        for net_name, buy_net in buy_nets.items():
            if not buy_net["withdraw"]:
                continue
            sell_net = sell_nets.get(net_name)
            if sell_net and sell_net["deposit"]:
                candidates.append((net_name, buy_net["fee"]))
        if candidates:
            candidates.sort(key=lambda x: x[1])
            return candidates[0]

        # Фолбэк: если одна из сторон не отдала network details, но top-level allow
        # — берём данные с той стороны, что отдала
        if buy_nets and not sell_nets and sell_info.get("top_deposit"):
            for net_name, buy_net in buy_nets.items():
                if buy_net["withdraw"]:
                    return (net_name, buy_net["fee"])
        if sell_nets and not buy_nets and buy_info.get("top_withdraw"):
            for net_name, sell_net in sell_nets.items():
                if sell_net["deposit"]:
                    return (net_name, 0.0)
        if not buy_nets and not sell_nets:
            if buy_info.get("top_withdraw") and sell_info.get("top_deposit"):
                return ("default", 0.0)
        return None


cache = CurrenciesCache()
