# Файл: exchanges/base.py
from typing import Optional, List


class BaseExchange:
    """
    Абстрактный базовый класс для всех криптобирж Супер-Сканера.
    Гарантирует единый интерфейс сбора рыночных стаканов без приватных ключей.
    """
    def __init__(self, exchange_id: str, base_url: str, monitored_symbols: List[str]):
        self.exchange_id = exchange_id.lower()
        self.base_url = base_url.strip().rstrip("/")
        self.monitored_symbols = monitored_symbols

    async def init_exchange(self):
        """Асинхронная инициализация и проверка доступности шлюза биржи."""
        raise NotImplementedError

    async def fetch_order_book(self, symbol: str, limit: int) -> Optional[dict]:
        """Получение текущего стакана цен (унифицированный формат)."""
        raise NotImplementedError
