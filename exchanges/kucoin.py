import asyncio
from exchanges.base import BaseExchange

class KuCoinExchange(BaseExchange):
	def __init__(self):
		super().__init__(exchange_id='kucoin')

	async def init_exchange(self):
		print("✅ [KUCOIN Direct] Спотовое подключение по прямым URL успешно настроено.")

	async def fetch_order_book(self, symbol: str, limit: int = 5) -> dict:
		"""
		Прямой асинхронный запрос спотового стакана KuCoin.
		"""
		# Формат KuCoin спот требует дефис (например, "BTC-USDT")
		kucoin_pair = symbol.upper().replace('/', '-')
		
		# ОФИЦИАЛЬНЫЙ ПУБЛИЧНЫЙ СПОТОВЫЙ ЭНДПОИНТ KUCOIN
		url = "https://api.kucoin.com"
		params = {"symbol": kucoin_pair}
		
		raw_response = await self.network_client.fetch_json(url, params=params)
		if not raw_response or raw_response.get('code') != '200000':
			return None
			
		data = raw_response.get('data', {})
		if 'bids' not in data or 'asks' not in data:
			return None
			
		try:
			return {
				'bids': [[float(item[0]), float(item[1])] for item in data.get('bids', []) if item],
				'asks': [[float(item[0]), float(item[1])] for item in data.get('asks', []) if item],
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
