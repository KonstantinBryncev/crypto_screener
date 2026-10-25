import asyncio
from exchanges.base import BaseExchange

class BingXExchange(BaseExchange):
	def __init__(self):
		super().__init__(exchange_id='bingx')
		self.monitored_symbols = [
			"BTC/USDT", "ETH/USDT", "LTC/USDT", "XRP/USDT", 
			"SOL/USDT", "DOGE/USDT", "DOT/USDT", "LINK/USDT", 
			"AVAX/USDT", "TRX/USDT"
		]

	async def init_exchange(self):
		print("✅ [BINGX Direct] Спотовое прямое подключение успешно настроено.")

	async def fetch_order_book(self, symbol: str, limit: int = 5) -> dict:
		"""
		Прямой запрос спотового стакана BingX.
		"""
		# Спотовый формат BingX требует дефис (например, "BTC-USDT")
		bingx_pair = symbol.upper().replace('/', '-')
		
		# ОФИЦИАЛЬНЫЙ ТОРГОВЫЙ API ДОМЕН BINGX
		url = "https://api.bingx.com"
		params = {
			"symbol": bingx_pair,
			"limit": limit
		}
		
		raw_response = await self.network_client.fetch_json(url, params=params)
		if not raw_response or 'data' not in raw_response:
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
