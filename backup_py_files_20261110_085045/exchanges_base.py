# Модуль: exchanges/base.py
from typing import List, Optional, Dict
# run_arbitrage.py
import sys
import asyncio  # <-- УБЕДИТЕСЬ, ЧТО ЭТА СТРОКА ТУТ ЕСТЬ
import logging
import warnings
import os
import json

class BaseExchange:
    """
    Абстрактный базовый класс для всех криптобирж.
    Определяет единый интерфейс взаимодействия.
    """
    def __init__(self, exchange_id: str, base_url: str, monitored_symbols: List[str]):
        self.exchange_id = exchange_id
        self.base_url = base_url
        self.monitored_symbols = monitored_symbols

    async def init_exchange(self):
        """Инициализация коннектора"""
        raise NotImplementedError

    async def fetch_order_book(self, symbol: str, limit: int = 5) -> Optional[dict]:
        """Получение биржевого стакана"""
        raise NotImplementedError

    async def fetch_balances(self) -> Dict[str, float]:
        """Получение балансов аккаунта"""
        raise NotImplementedError

    async def fetch_tickers(self) -> dict:
        """Резервный метод для получения тикеров"""
        raise NotImplementedError
