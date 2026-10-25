import asyncio
import logging
import time
import hmac
import hashlib
from typing import Dict, Any, List, Optional
from exchanges.base import BaseExchange

logger = logging.getLogger("GateExchange")

class GateExchange(BaseExchange):
	"""
	Модуль прямого асинхронного взаимодействия с API Gate.io V4 REST.
	"""
	
	def __init__(self, network_client, base_url: str, monitored_symbols: List[str], api_key: str = "", api_secret: str = ""):
		super().__init__(exchange_id='gate', base_url=base_url, monitored_symbols=monitored_symbols)
		self.network_client = network_client
		self.api_key = api_key
		self.api_secret = api_secret

	async def init_exchange(self):
		print(f"✅ [GATE.IO] Успешно инициализирован хост: {self.base_url}")

	def _generate_sign(self, method: str, resource_path: str, query_string: str, body_str: str, timestamp: str) -> Dict[str, str]:
		"""Генерация подписи по протоколу аутентификации Gate V4 (HMAC-SHA512)"""
		hashed_body = hashlib.sha512(body_str.encode('utf-8')).hexdigest()
		signature_string = f"{method}\n{resource_path}\n{query_string}\n{hashed_body}\n{timestamp}"
		sign = hmac.new(self.api_secret.encode('utf-8'), signature_string.encode('utf-8'), hashlib.sha512).hexdigest()
		return {"KEY": self.api_key, "SIGN": sign, "Timestamp": timestamp, "Content-Type": "application/json"}

	async def fetch_order_book(self, symbol: str, limit: int = 5) -> Optional[dict]:
		"""Отладочный запрос стакана ордеров Gate.io с выводом сырых данных."""
		gate_pair = symbol.upper().replace('/', '_')
		url = f"{self.base_url}/spot/order_book"
		
		params = {"currency_pair": gate_pair, "limit": limit}
		
		gate_headers = {
			"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
			"Accept": "application/json, text/plain, */*",
			"Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8"
		}
		
		raw_book = await self.network_client.fetch_json(
			url=url, 
			method="GET", 
			params=params, 
			headers=gate_headers
		)
		
		
		if not raw_book or 'bids' not in raw_book or 'asks' not in raw_book:
			return None
			
		try:
			return {
				'bids': [[float(item[0]), float(item[1])] for item in raw_book.get('bids', []) if item and len(item) >= 2],
				'asks': [[float(item[0]), float(item[1])] for item in raw_book.get('asks', []) if item and len(item) >= 2],
				'symbol': symbol.upper(),
				'timestamp': int(time.time() * 1000),
				'type': 'spot',
				'spot': True
			}
		except Exception as e:
			logger.error(f"Ошибка парсинга стакана Gate для {symbol}: {e}")
			return None


	async def fetch_candles(self, symbol: str, timeframe: str = "1m", limit: int = 20) -> Optional[List[List[float]]]:
		gate_pair = symbol.upper().replace('/', '_')
		url = f"{self.base_url}/spot/candlesticks"
		
		params = {"currency_pair": gate_pair, "interval": timeframe, "limit": limit}
		
		raw_candles = await self.network_client.fetch_json(url=url, method="GET", params=params)
		
		if not raw_candles or not isinstance(raw_candles, list):
			return None
			
		try:
			formatted_candles = []
			for c in raw_candles:
				if len(c) >= 6:
					formatted_candles.append([
						float(c[0]) * 1000, float(c[1]), float(c[2]), float(c[3]), float(c[4]), float(c[5])
					])
			return formatted_candles
		except Exception as e:
			logger.error(f"Ошибка парсинга свечей Gate для {symbol}: {e}")
			return None

	async def fetch_balances(self) -> Dict[str, float]:
		if not self.api_key or not self.api_secret:
			return {"USDT": 0.0}
			
		resource_path = "/spot/accounts"
		url = f"{self.base_url}{resource_path}"
		timestamp = str(int(time.time()))
		
		headers = self._generate_sign("GET", f"/api/v4{resource_path}", "", "", timestamp)
		
		raw_response = await self.network_client.fetch_json(url=url, method="GET", headers=headers)
		balances = {"USDT": 0.0}
		
		if not raw_response or (isinstance(raw_response, dict) and "label" in raw_response):
			return balances
			
		try:
			if isinstance(raw_response, list):
				for account in raw_response:
					asset_name = account.get("currency", "").upper()
					available_amount = float(account.get("available", 0.0))
					balances[asset_name] = available_amount
			return balances
		except Exception as e:
			logger.error(f"Ошибка парсинга balances Gate: {e}")
			return balances

	async def fetch_tickers(self) -> dict:
		return {}
