# Модуль: exchanges/base.py
from abc import ABC, abstractmethod
from typing import Dict, Optional, List
import ccxt.async_support as ccxt
from network.client import AsyncHttpClient

class BaseExchange(ABC):
	"""
	Абстрактный базовый класс для всех криптобирж в проекте.
	Класс наследуется от ABC (Abstract Base Class), что запрещает создавать 
	его объекты напрямую. Он служит исключительно шаблоном-инструкцией.
	"""

	def __init__(self, exchange_id: str):
		"""
		Конструктор базового класса.
		:param exchange_id: Уникальный идентификатор биржи в системе CCXT (например, 'bybit', 'binance')
		"""
		self.exchange_id: str = exchange_id
		
		# Переменная, где будет храниться экземпляр асинхронного класса биржи от CCXT
		self.api: Optional[ccxt.Exchange] = None
		
		# Получаем наш синглтон асинхронного HTTP-клиента из Задачи 1
		self.network_client = AsyncHttpClient()

	async def init_exchange(self):
		"""
		Инициализирует асинхронное подключение к бирже через CCXT.
		Этот метод мы вызываем один раз при старте скринера.
		"""
		if self.api is None:
			# Получаем класс биржи динамически по её названию из библиотеки ccxt.async_support
			exchange_class = getattr(ccxt, self.exchange_id)
			
			# Инициализируем биржу с базовыми настройками оптимизации ресурсов
			self.api = exchange_class({
				'enableRateLimit': True,  # Автоматический контроль частоты запросов
				'timeout': 10000,         # Таймаут запроса — 10 секунд
				# ЖЕСТКО УКАЗЫВАЕМ РЫНОК: Заставляем CCXT работать со Спотом, а не с Фьючерсами
				'options': {
					'defaultType': 'spot'
				}
			})
			
			# Интеграция прокси (остается без изменений)
			proxy = self.network_client._get_random_proxy()
			if proxy:
				self.api.proxies = {'http': proxy, 'https': proxy}
				print(f"🌐 [{self.exchange_id.upper()}] Подключение настроено через прокси: {proxy}")
			else:
				print(f"🔒 [{self.exchange_id.upper()}] Подключение настроено напрямую (без прокси).")


	@abstractmethod
	async def fetch_tickers(self) -> Dict[str, Dict[str, float]]:
		"""
		Абстрактный метод для получения текущих цен и объемов (тикеров).
		
		Декоратор @abstractmethod ЖЕСТКО ОБЯЗЫВАЕТ любой дочерний класс 
		(например, BybitExchange) реализовать этот метод внутри себя.
		Если мы забудем его написать в bybit.py, Python выдаст ошибку еще при запуске.
		
		Каждая биржа должна возвращать данные в ЕДИНОМ СТАНДАРТЕ нашего скринера:
		{
			'BTC/USDT': {'price': 65000.0, 'volume': 1200.5},
			'ETH/USDT': {'price': 3450.2, 'volume': 8500.1}
		}
		Такой подход на чистых словарях Python экономит кучу ОЗУ по сравнению с pandas!
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
