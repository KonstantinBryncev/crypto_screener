# Модуль: exchanges/gate.py
import ccxt.async_support as ccxt
import logging
from exchanges.base import BaseExchange

logger = logging.getLogger("GateExchange")

class GateExchange(BaseExchange):
	"""
	Асинхронный коннектор к бирже Gate.io на базе ccxt.
	"""
	def __init__(self):
		super().__init__('gate')
		self.name = "gate"
		self.api = None

	async def init_exchange(self):
		"""
		Инициализация сессии Gate.io со спотовыми настройками по умолчанию.
		"""
		if self.api is None:
			self.api = ccxt.gate({
				'options': {
					'defaultType': 'spot',
					'loadCurrencies': False,  # Отключаем автоматическую подгрузку
					'loadMarkets': False
				},
				'enableRateLimit': True,
				'adjustForTimeDifference': True
			})
			self.api.timeout = 20000  # Защита от таймаутов сетей в РФ
			
			# ЖЕСТКИЙ ХАК ДЛЯ ОБХОДА ОШИБКИ /currencies БЕЗ ПРОКСИ:
			# Искусственно создаем локальный кэш валют в памяти ccxt,
			# чтобы библиотека думала, что справочник уже успешно загружен.
			self.api.currencies = {
				'USDT': {'id': 'USDT', 'code': 'USDT'},
				'BTC': {'id': 'BTC', 'code': 'BTC'},
				'ETH': {'id': 'ETH', 'code': 'ETH'},
				'LTC': {'id': 'LTC', 'code': 'LTC'},
				'XRP': {'id': 'XRP', 'code': 'XRP'},
				'SOL': {'id': 'SOL', 'code': 'SOL'},
				'DOGE': {'id': 'DOGE', 'code': 'DOGE'},
				'DOT': {'id': 'DOT', 'code': 'DOT'},
				'LINK': {'id': 'LINK', 'code': 'LINK'},
				'AVAX': {'id': 'AVAX', 'code': 'AVAX'},
				'TRX': {'id': 'TRX', 'code': 'TRX'}
			}
			
		return self.api

	async def fetch_order_book(self, symbol: str, limit: int = 5):
		"""
		Безопасное получение стакана для Gate.io (Арбитраж).
		"""
		if not self.api:
			await self.init_exchange()
			
		try:
			return await self.api.fetch_order_book(symbol, limit=limit)
		except Exception as e:
			raise e

	async def fetch_tickers(self):
		"""
		Реализация обязательного абстрактного метода родительского класса.
		"""
		if not self.api:
			await self.api.init_exchange()
		try:
			return await self.api.fetch_tickers()
		except Exception:
			return {}

	async def close(self):
		"""
		Закрытие асинхронной HTTP-сессии Gate.io при остановке бота.
		"""
		if self.api:
			await self.api.close()
			print("🔌 [GATE] Асинхронное подключение к API успешно закрыто.")
