"""CCXT-подключения к биржам и кэш балансов для авто-трейдера."""
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import ccxt.async_support as ccxt
from loguru import logger


@dataclass
class ExchangeBalance:
    exchange_id: str
    usdt: float = 0.0
    coins: dict[str, float] = field(default_factory=dict)
    updated_at: Optional[datetime] = None

    def coin(self, symbol: str) -> float:
        return self.coins.get(symbol.upper(), 0.0)

    def total_usd_estimate(self, prices: dict[str, float]) -> float:
        """Приблизительная общая сумма в USD."""
        total = self.usdt
        for coin, amount in self.coins.items():
            price = prices.get(coin, 0.0)
            total += amount * price
        return total


class TraderAccounts:
    """Авторизованные подключения к биржам трейдера."""

    def __init__(self, exchange_configs: dict[str, dict]):
        """
        exchange_configs: {
            "bybit":   {"api_key": "...", "api_secret": "..."},
            "binance": {"api_key": "...", "api_secret": "..."},
            "okx":     {"api_key": "...", "api_secret": "...", "passphrase": "..."},
        }
        """
        self._configs = exchange_configs
        self._instances: dict[str, ccxt.Exchange] = {}
        self._balances: dict[str, ExchangeBalance] = {}
        self._lock = asyncio.Lock()

    def enabled_exchanges(self) -> list[str]:
        return list(self._configs.keys())

    def get_exchange(self, exchange_id: str) -> ccxt.Exchange:
        if exchange_id not in self._instances:
            self._instances[exchange_id] = self._make_instance(exchange_id)
        return self._instances[exchange_id]

    def _make_instance(self, exchange_id: str) -> ccxt.Exchange:
        cfg = self._configs[exchange_id]
        cls = getattr(ccxt, exchange_id, None)
        if cls is None:
            raise ValueError(f"Неизвестная биржа: {exchange_id}")
        params = {
            "apiKey": cfg["api_key"],
            "secret": cfg["api_secret"],
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
        }
        if "passphrase" in cfg:
            params["password"] = cfg["passphrase"]
        return cls(params)

    async def fetch_balance(self, exchange_id: str) -> ExchangeBalance:
        ex = self.get_exchange(exchange_id)
        try:
            raw = await ex.fetch_balance()
            total = raw.get("total", {})
            usdt = float(total.get("USDT", 0) or 0)
            coins = {
                k: float(v or 0)
                for k, v in total.items()
                if k != "USDT" and float(v or 0) > 1e-9
            }
            bal = ExchangeBalance(
                exchange_id=exchange_id,
                usdt=usdt,
                coins=coins,
                updated_at=datetime.now(timezone.utc),
            )
            async with self._lock:
                self._balances[exchange_id] = bal
            return bal
        except Exception as e:
            logger.error(f"fetch_balance [{exchange_id}]: {e}")
            return self._balances.get(exchange_id, ExchangeBalance(exchange_id))

    async def fetch_all_balances(self) -> dict[str, ExchangeBalance]:
        tasks = [self.fetch_balance(ex) for ex in self._configs]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        out: dict[str, ExchangeBalance] = {}
        for ex_id, res in zip(self._configs.keys(), results):
            if isinstance(res, ExchangeBalance):
                out[ex_id] = res
        return out

    def cached_balance(self, exchange_id: str) -> ExchangeBalance:
        return self._balances.get(exchange_id, ExchangeBalance(exchange_id))

    async def load_markets_all(self) -> None:
        """Предзагрузка маркетов для всех бирж."""
        tasks = []
        for ex_id in self._configs:
            ex = self.get_exchange(ex_id)
            tasks.append(ex.load_markets())
        await asyncio.gather(*tasks, return_exceptions=True)

    async def close(self) -> None:
        for ex in self._instances.values():
            try:
                await ex.close()
            except Exception:
                pass
