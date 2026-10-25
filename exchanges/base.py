from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional

class BaseExchange(ABC):
	"""
	Абстрактный класс-интерфейс. Гарантирует, что коннектор любой биржи 
	будет иметь одинаковый набор методов и принимать конфигурацию из JSON.
	"""

	def __init__(self, exchange_id: str, base_url: str, monitored_symbols: List[str]):
		"""
		Конструктор базового класса. Сюда передаются настройки из config_bot.json
		"""
		self.exchange_id = exchange_id.lower()
		# rstrip('/') страхует от дублирования слешей при сборке конечных путей URL
		self.base_url = base_url.strip().rstrip('/')  
		self.monitored_symbols = monitored_symbols

	@abstractmethod
	async def init_exchange(self):
		"""Асинхронный запуск/логирование готовности модуля биржи"""
		pass

	@abstractmethod
	async def fetch_order_book(self, symbol: str, limit: int = 5) -> Optional[Dict[str, Any]]:
		"""Получение текущего стакана цен (унифицированный формат)"""
		pass

	@abstractmethod
	async def fetch_candles(self, symbol: str, timeframe: str = "1m", limit: int = 20) -> Optional[List[List[float]]]:
		"""Получение исторических свечей для выявления пампов/дампов"""
		pass

	@abstractmethod
	async def fetch_balances(self) -> Dict[str, float]:
		"""Запрос свободных балансов на спотовом кошельке аккаунта"""
		pass

	@abstractmethod
	async def fetch_tickers(self) -> dict:
		"""Резервный метод для расширения интерфейса структуры"""
		pass
