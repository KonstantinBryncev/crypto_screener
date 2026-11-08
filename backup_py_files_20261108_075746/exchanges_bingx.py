import asyncio
import logging
import time
import hmac
import hashlib
from typing import Dict, Any, List, Optional
from exchanges.base import BaseExchange

logger = logging.getLogger("BingXExchange")

class BingXExchange(BaseExchange):
	"""
	Коннектор к бирже BingX, работающий напрямую через официальный REST API.
	"""
	
	def __init__(self, network_client, base_url: str, monitored_symbols: List[str], api_key: str = "", api_secret: str = ""):
		super().__init__(exchange_id='bingx', base_url=base_url, monitored_symbols=monitored_symbols)
		self.network_client = network_client
		self.api_key = api_key
		self.api_secret = api_secret

	async def init_exchange(self):
		print(f"✅ [BINGX] Успешно инициализирован хост: {self.base_url}")

	def _generate_signature(self, params_str: str) -> str:
		return hmac.new(self.api_secret.encode('utf-8'), params_str.encode('utf-8'), hashlib.sha256).hexdigest()

	async def fetch_order_book(self, symbol: str, limit: int = 5) -> Optional[dict]:
		bingx_pair = symbol.upper().replace('/', '-')
		url = f"{self.base_url}/openApi/spot/v1/market/depth"
		params = {"symbol": bingx_pair, "limit": limit}
		
		raw_response = await self.network_client.fetch_json(url, params=params)
		if not raw_response or 'data' not in raw_response:
			return None
			
		data = raw_response.get('data', {})
		try:
			return {
				'bids': [[float(item[0]), float(item[1])] for item in data.get('bids', []) if item],
				'asks': [[float(item[0]), float(item[1])] for item in data.get('asks', []) if item],
				'symbol': symbol.upper(),
				'timestamp': int(data.get('ts', time.time() * 1000)),
				'type': 'spot',
				'spot': True
			}
		except Exception as e:
			logger.error(f"Ошибка при конвертации типов стакана BingX для {symbol}: {e}")
			return None

	async def fetch_balances(self) -> Dict[str, float]:
		"""Запрос доступных балансов спотового кошелька BingX через актуальный эндпоинт."""
		if not self.api_key or not self.api_secret:
			return {"USDT": 0.0}
			
		url = f"{self.base_url}/openApi/v1/asset/transfer/assetInfo"
		timestamp = str(int(time.time() * 1000))
		
		params_str = f"timestamp={timestamp}"
		signature = self._generate_signature(params_str)
		
		params = {
			"timestamp": timestamp,
			"signature": signature
		}
		
		headers = {
			"X-BX-APIKEY": str(self.api_key),
			"Content-Type": "application/json"
		}
		
		raw_response = await self.network_client.fetch_json(url=url, method="GET", params=params, headers=headers)
		balances = {"USDT": 0.0}
		
		if not raw_response or not isinstance(raw_response, dict) or raw_response.get('code') != 0:
			return balances
			
		try:
			data_list = raw_response.get('data', [])
			for item in data_list:
				asset_name = item.get('asset', '').upper()
				free_balance = float(item.get('avail', 0.0))
				if free_balance > 0:
					balances[asset_name] = free_balance
			return balances
		except Exception as e:
			logger.error(f"Ошибка парсинга актуальных балансов BingX: {e}")
			return balances

	async def fetch_tickers(self) -> dict:
		"""
		Обязательный абстрактный метод структуры интерфейса BaseExchange.
		Реализует заглушку для сохранения целостности архитектуры.
		"""
		return {}
