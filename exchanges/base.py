# Файл: exchanges/base.py
from typing import List, Optional, Dict

class BaseExchange:
    """
    Абстрактный базовый класс для всех криптобирж проекта.
    Гарантирует единый интерфейс вызова методов сбора рыночных данных.
    """
    def __init__(self, exchange_id: str, base_url: str, monitored_symbols: List[str]):
        self.exchange_id = exchange_id.lower()
        self.base_url = base_url.strip().rstrip('/')
        self.monitored_symbols = monitored_symbols

    async def init_exchange(self):
        """Асинхронная инициализация и проверка доступности шлюза биржи"""
        raise NotImplementedError

    async def fetch_order_book(self, symbol: str, limit: int = 5) -> Optional[dict]:
        """Получение текущего стакана цен (унифицированный формат)"""
        raise NotImplementedError

    async def fetch_balances(self) -> Dict[str, float]:
        """Запрос свободных балансов на спотовом кошельке аккаунта"""
        raise NotImplementedError

    async def fetch_tickers(self) -> dict:
        """Резервный метод для получения общих рыночных тикеров"""
        raise NotImplementedError
