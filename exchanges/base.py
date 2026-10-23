# Модуль: exchanges/base.py
from abc import ABC, abstractmethod
from typing import Dict, Optional, List
import ccxt.async_support as ccxt
from network.client import AsyncHttpClient
import logging

logger = logging.getLogger("BaseExchange")

class BaseExchange(ABC):
	"""
	Абстрактный базовый класс для всех криптобирж в проекте.
	Служит шаблоном-инструкцией и содержит общие сетевые методы.
	"""

	def __init__(self, exchange_id: str):
		"""
		Конструктор базового класса.
		:param exchange_id: Уникальный идентификатор биржи в системе CCXT (например, 'bybit', 'bingx')
		"""
		self.exchange_id: str = exchange_id
		
		# Переменная, где будет храниться экземпляр асинхронного класса биржи от CCXT
		self.api: Optional[ccxt.Exchange] = None
		
		# Получаем наш синглтон асинхронного HTTP-клиента
		self.network_client = AsyncHttpClient()

	async def init_exchange(self):
		"""
		Инициализирует асинхронное подключение к бирже через CCXT.
		Этот метод мы вызываем один раз при старте скринера.
		"""
		if self.api is None:
			# Получаем класс биржи динамически по её названию из библиотеки ccxt.async_support
			exchange_class = getattr(ccxt, self.exchange_id)
			
			# Инициализируем биржу с жестким ограничением рынков
			self.api = exchange_class({
				'enableRateLimit': True,  # Автоматический контроль частоты запросов
				'timeout': 10000,         # Таймаут запроса — 10 секунд
				# ЖЕСТКАЯ СТАБИЛИЗАЦИЯ НА СПОТОВОМ РЫНКЕ
				'options': {
					'defaultType': 'spot',        # Базовый тип рынка для Bybit/OKX/KuCoin
					'adjustForTimeDifference': True # Защита от рассинхронизации времени Windows с биржей
				}
			})
			
			# Кастомная заплатка специально для BingX, так как CCXT драйвер BingX 
			# иногда игнорирует defaultType и требует явного переключения подтипа
			if self.exchange_id == 'bingx':
				self.api.options['type'] = 'spot'
				self.api.options['subType'] = 'spot'
			
			# Интеграция прокси
			proxy = self.network_client._get_random_proxy()
			if proxy:
				self.api.proxies = {'http': proxy, 'https': proxy}
				print(f"🌐 [{self.exchange_id.upper()}] Подключение настроено через прокси: {proxy}")
			else:
				print(f"🔒 [{self.exchange_id.upper()}] Подключение настроено напрямую (без прокси).")


	async def fetch_order_book(self, symbol: str, limit: int = 5) -> Optional[dict]:
		"""
		Общий асинхронный метод получения стакана ордеров (Orderbook) для арбитража.
		Подходит для всех нативных бирж CCXT. Глубина ограничена до 5 ордеров для экономии ОЗУ.
		"""
		if not self.api:
			return None
		try:
			return await self.api.fetch_order_book(symbol, limit=limit)
		except Exception as e:
			logger.warning(f"Ошибка получения стакана {symbol} с {self.exchange_id.upper()}: {e}")
			return None

	@abstractmethod
	async def fetch_tickers(self) -> Dict[str, Dict[str, float]]:
		"""
		Абстрактный метод для получения текущих цен и объемов (тикеров).
		Обязателен к реализации в дочерних классах.
		"""
		pass

	async def close(self):
		"""
		Корректное закрытие асинхронных коннектов биржи.
		Освобождает оперативную память и закрывает сетевые сокеты внутри CCXT.
		"""
		if self.api:
			await self.api.close()
			print(f"🛑 [{self.exchange_id.upper()}] Асинхронное подключение к API успешно закрыто.")
