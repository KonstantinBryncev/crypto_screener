from abc import ABC, abstractmethod
from typing import Dict, Optional, List
from network.client import AsyncHttpClient
import logging

logger = logging.getLogger("BaseExchange")

class BaseExchange(ABC):
    """
    Абстрактный базовый класс для всех криптобирж в проекте на чистом aiohttp.
    Служит шаблоном-инструкцией и содержит общий сетевой клиент.
    """

    def __init__(self, exchange_id: str):
        """
        Конструктор базового класса.
        :param exchange_id: Уникальный идентификатор биржи в системе (bybit, bingx, kucoin, gate)
        """
        self.exchange_id: str = exchange_id
        self.network_client = AsyncHttpClient()

    @abstractmethod
    async def init_exchange(self):
        """Инициализация подключения или логических структур на старте"""
        pass

    @abstractmethod
    async def fetch_order_book(self, symbol: str, limit: int = 5) -> Optional[dict]:
        """
        Абстрактный метод получения спотового стакана ордеров (Orderbook) для арбитража.
        Каждая биржа реализует его через свои прямые эндпоинты.
        """
        pass

    @abstractmethod
    async def fetch_tickers(self) -> Dict[str, Dict[str, float]]:
        """
        Абстрактный метод для получения текущих цен и объемов (тикеров).
        """
        pass

    async def close(self):
        """Уведомление о закрытии коннектора биржи"""
        print(f"🛑 [{self.exchange_id.upper()}] Коннектор успешно остановлен.")
