# Файл: exchanges/kucoin.py
import logging
import time
from typing import Optional, List
from exchanges.base import BaseExchange

logger = logging.getLogger("KuCoinExchange")

class KuCoinExchange(BaseExchange):
	def __init__(self, network_client, base_url: str, monitored_symbols: List[str], **kwargs):
		super().__init__(exchange_id='kucoin', base_url=base_url, monitored_symbols=monitored_symbols)
		self.network_client = network_client

	async def init_exchange(self):
		print("🔹 [KUCOIN] Коннектор успешно инициализирован.")
		return True

	async def fetch_order_book(self, symbol: str, limit: int = 5) -> Optional[dict]:
		formatted_symbol = symbol.replace("/", "-").upper()
		# Публичный и стабильный эндпоинт, который не банит по лимитам
		url = f"{self.base_url}/api/v1/market/orderbook/level2_20?symbol={formatted_symbol}"
		
		raw_response = await self.network_client.fetch_json(url, method="GET")
		if not raw_response or not isinstance(raw_response, dict):
			return None
			
		data = raw_response.get('data')
		if not data or not isinstance(data, dict):
			return None
			
		try:
			return {
				'bids': [[float(p), float(s)] for p, s in data.get('bids', []) if p and s][:limit],
				'asks': [[float(p), float(s)] for p, s in data.get('asks', []) if p and s][:limit],
				'symbol': symbol.upper(),
				'timestamp': int(data.get('time', time.time() * 1000)),
				'type': 'spot',
				'spot': True
			}
		except Exception as e:
			logger.error(f"Ошибка парсинга стакана KuCoin для {symbol}: {e}")
			return None

	async def fetch_balances(self):
		return {"USDT": 0.0}

	async def fetch_tickers(self):
		return {}
