import asyncio
from exchanges.base import BaseExchange

class GateExchange(BaseExchange):
	def __init__(self):
		"""
		Инициализация обертки для биржи Gate.io на чистом REST API (aiohttp).
		"""
		super().__init__(exchange_id='gate')
		self.monitored_symbols = [
			"BTC/USDT", "ETH/USDT", "LTC/USDT", "XRP/USDT", 
			"SOL/USDT", "DOGE/USDT", "DOT/USDT", "LINK/USDT", 
			"AVAX/USDT", "TRX/USDT"
		]

	async def init_exchange(self):
		print("✅ [GATE Direct] Прямой спотовый эндпоинт успешно настроен.")

	async def fetch_order_book(self, symbol: str, limit: int = 5) -> dict:
		"""
		Точечный асинхронный запрос спотового стакана Gate.io.
		"""
		# Преобразуем формат под спотовый API Gate (например, "BTC_USDT")
		gate_pair = symbol.upper().replace('/', '_')
		
		# ОФИЦИАЛЬНЫЙ API ДОМЕН GATE.IO
		url = "https://api.gateio.ws"
		params = {
			"currency_pair": gate_pair,
			"limit": limit
		}
		
		raw_book = await self.network_client.fetch_json(url, params=params)
		if not raw_book or 'bids' not in raw_book or 'asks' not in raw_book:
			return None
			
		try:
			return {
				'bids': [[float(item[0]), float(item[1])] for item in raw_book.get('bids', []) if item],
				'asks': [[float(item[0]), float(item[1])] for item in raw_book.get('asks', []) if item],
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
