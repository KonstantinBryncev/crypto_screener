import asyncio
from exchanges.base import BaseExchange

class BybitExchange(BaseExchange):
	def __init__(self):
		super().__init__(exchange_id='bybit')

	async def init_exchange(self):
		print("✅ [BYBIT Direct] Публичный спотовый REST-режим успешно запущен.")

	async def fetch_order_book(self, symbol: str, limit: int = 5) -> dict:
		"""
		Прямой запрос спотового стакана Bybit V5.
		"""
		# Спотовый формат Bybit пишется слитно (например, "BTCUSDT")
		bybit_pair = symbol.upper().replace('/', '').replace('_', '')
		
		# ОФИЦИАЛЬНЫЙ ТОРГОВЫЙ API ДОМЕН BYBIT
		url = "https://api.bybit.com"
		params = {
			"category": "spot",
			"symbol": bybit_pair,
			"limit": limit
		}
		
		raw_response = await self.network_client.fetch_json(url, params=params)
		if not raw_response or raw_response.get('retCode') != 0:
			return None
			
		result = raw_response.get('result', {})
		if 'b' not in result or 'a' not in result:
			return None
			
		try:
			return {
				'bids': [[float(item[0]), float(item[1])] for item in result.get('b', []) if item],
				'asks': [[float(item[0]), float(item[1])] for item in result.get('a', []) if item],
				'symbol': symbol.upper(),
				'timestamp': None,
				'datetime': None,
				'contract': False,
				'linear': False,
				'inverse': False,
				'type': 'spot',
				'spot': True
			}
		except Exception:
			return None

	async def fetch_tickers(self) -> dict:
		return {}
