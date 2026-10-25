# Модуль: exchanges/bingx.py
import ccxt.async_support as ccxt
from typing import Dict, Optional
from exchanges.base import BaseExchange
import asyncio
import logging

logger = logging.getLogger("BingXExchange")

class BingXExchange(BaseExchange):
	"""
	Класс-коннектор для работы с биржей BingX.
	Наследуется от BaseExchange и точечно собирает данные для экономии ресурсов.
	"""

	def __init__(self):
		super().__init__(exchange_id='bingx')
		self.name = "bingx"
		self.api = None
		# Список целевых монет для арбитража
		self.target_symbols = ['BTC/USDT', 'ETH/USDT', 'LTC/USDT', 'XRP/USDT', 'SOL/USDT', 'DOGE/USDT', 'DOT/USDT', 'LINK/USDT', 'AVAX/USDT', 'TRX/USDT']

	async def init_exchange(self):
		"""
		Инициализация асинции сессии BingX со спотовыми настройками по умолчанию.
		"""
		if self.api is None:
			self.api = ccxt.bingx({
				'options': {
					'defaultType': 'spot',   # Работаем строго на спотовом рынке
					'loadMarkets': False     # Отключаем тяжелые внутренние запросы контрактов swap/*
				},
				'enableRateLimit': True,     # Встроенная защита ccxt от Rate Limit
				'adjustForTimeDifference': True
			})
			self.api.timeout = 20000         # Защита от таймаутов сети в РФ
			
		return self.api

	async def fetch_order_book(self, symbol: str, limit: int = 5):
		"""
		Безопасное получение стакана для BingX (Арбитраж).
		"""
		if not self.api:
			await self.init_exchange()
			
		try:
			return await self.api.fetch_order_book(symbol, limit=limit)
		except Exception as e:
			raise e

	async def _fetch_single_ticker(self, symbol: str) -> Optional[dict]:
		"""Безопасный точечный запрос тикера одной монеты"""
		try:
			if not self.api:
				await self.init_exchange()
			ticker = await self.api.fetch_ticker(symbol)
			if ticker.get('last') is not None:
				return {
					'price': float(ticker['last']),
					'volume': float(ticker.get('quoteVolume', 0.0))
				}
		except Exception as e:
			logger.warning(f"Не удалось получить тикер {symbol} с BingX: {e}")
		return None

	async def fetch_tickers(self) -> Dict[str, Dict[str, float]]:
		"""
		Асинхронно собирает тикеры только для target_symbols параллельными запросами.
		Идеально для экономии ОЗУ и обхода ограничений общего эндпоинта.
		"""
		if not self.api:
			await self.init_exchange()

		try:
			tasks = [self._fetch_single_ticker(symbol) for symbol in self.target_symbols]
			results = await asyncio.gather(*tasks)
			
			valid_tickers = {}
			for symbol, res in zip(self.target_symbols, results):
				if res:
					valid_tickers[symbol] = res
					
			return valid_tickers

		except Exception as e:
			logger.error(f"Глобальная ошибка сбора тикеров BingX: {e}")
			return {}

	async def close(self):
		"""
		Закрытие асинхронной HTTP-сессии BingX при остановке бота.
		"""
		if self.api:
			await self.api.close()
			print("🔌 [BINGX] Асинхронное подключение к API успешно закрыто.")
