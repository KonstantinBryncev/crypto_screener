# Модуль: exchanges/bingx.py
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
		# Список целевых монет для арбитража
		self.target_symbols = ['BTC/USDT', 'ETH/USDT', 'LTC/USDT', 'XRP/USDT']

	async def _fetch_single_ticker(self, symbol: str) -> Optional[dict]:
		"""Безопасный точечный запрос тикера одной монеты"""
		try:
			# fetch_ticker (в единственном числе) запрашивает данные только по одной паре
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
			logger.error("API биржи BingX не инициализировано!")
			return {}

		try:
			# Создаем задачи на опрос только наших 4 монет параллельно
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
