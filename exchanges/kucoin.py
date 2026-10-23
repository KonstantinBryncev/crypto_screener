# Модуль: exchanges/kucoin.py
from typing import Dict, Optional
from exchanges.base import BaseExchange
import asyncio
import logging

logger = logging.getLogger("KuCoinExchange")

class KuCoinExchange(BaseExchange):
	"""
	Класс-коннектор для работы со спотовым рынком биржи KuCoin.
	Наследуется от BaseExchange и оптимизирован для работы без прокси.
	"""

	def __init__(self):
		super().__init__(exchange_id='kucoin')
		self.target_symbols = ['BTC/USDT', 'ETH/USDT', 'LTC/USDT', 'XRP/USDT']

	async def init_exchange(self):
		"""
		Переопределяем инициализацию, чтобы ЖЕСТКО запретить KuCoin 
		скачивать справочник валют, который блокируется Cloudflare.
		"""
		await super().init_exchange()
		if self.api:
			# ОТКЛЮЧАЕМ тяжелый служебный запрос к api/v3/currencies
			self.api.options['preloadCurrencies'] = False
			self.api.options['defaultType'] = 'spot'

	async def _fetch_single_ticker(self, symbol: str) -> Optional[dict]:
		"""Безопасный точечный запрос тикера одной монеты с KuCoin"""
		if not self.api:
			return None
		try:
			ticker = await self.api.fetch_ticker(symbol)
			if ticker and ticker.get('last') is not None:
				return {
					'price': float(ticker['last']),
					'volume': float(ticker.get('quoteVolume', 0.0))
				}
		except Exception:
			pass
		return None

	async def fetch_tickers(self) -> Dict[str, Dict[str, float]]:
		"""
		Асинхронно собирает тикеры KuCoin только для target_symbols параллельными запросами.
		"""
		if not self.api:
			return {}

		try:
			tasks = [self._fetch_single_ticker(symbol) for symbol in self.target_symbols]
			results = await asyncio.gather(*tasks)
			
			valid_tickers = {}
			for symbol, res in zip(self.target_symbols, results):
				if res:
					valid_tickers[symbol] = res
					
			return valid_tickers

		except Exception:
			return {}
