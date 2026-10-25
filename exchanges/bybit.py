import asyncio
import logging
import time
import hmac
import hashlib
from typing import Dict, Any, List, Optional
from exchanges.base import BaseExchange

logger = logging.getLogger("BybitExchange")

class BybitExchange(BaseExchange):
	"""
	Модуль прямого асинхронного взаимодействия со спотовым шлюзом Bybit V5.
	"""
	
	def __init__(self, network_client, base_url: str, monitored_symbols: List[str], api_key: str = "", api_secret: str = ""):
		super().__init__(exchange_id='bybit', base_url=base_url, monitored_symbols=monitored_symbols)
		self.network_client = network_client
		self.api_key = api_key
		self.api_secret = api_secret

	async def init_exchange(self):
		print(f"✅ [BYBIT] Успешно инициализирован хост: {self.base_url}")

	def _generate_signature(self, timestamp: str, recv_window: str, params_str: str) -> str:
		val = timestamp + self.api_key + recv_window + params_str
		return hmac.new(self.api_secret.encode('utf-8'), val.encode('utf-8'), hashlib.sha256).hexdigest()

	def _create_auth_headers(self, params_str: str = "") -> Dict[str, str]:
		timestamp = str(int(time.time() * 1000))
		recv_window = "5000"
		signature = self._generate_signature(timestamp, recv_window, params_str)
		return {
			"X-BAPI-API-KEY": self.api_key,
			"X-BAPI-SIGN": signature,
			"X-BAPI-TIMESTAMP": timestamp,
			"X-BAPI-RECV-WINDOW": recv_window,
			"Content-Type": "application/json"
		}

	async def fetch_order_book(self, symbol: str, limit: int = 5) -> Optional[dict]:
		bybit_pair = symbol.upper().replace('/', '').replace('_', '')
		url = f"{self.base_url}/v5/market/orderbook"
		
		params = {"category": "spot", "symbol": bybit_pair, "limit": limit}
		raw_response = await self.network_client.fetch_json(url=url, method="GET", params=params)

		
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
				'timestamp': int(result.get('ts', time.time() * 1000)),
				'type': 'spot',
				'spot': True
			}
		except Exception as e:
			logger.error(f"Ошибка парсинга стакана Bybit для {symbol}: {e}")
			return None

	async def fetch_candles(self, symbol: str, timeframe: str = "1m", limit: int = 20) -> Optional[List[List[float]]]:
		bybit_pair = symbol.upper().replace('/', '').replace('_', '')
		url = f"{self.base_url}/v5/market/kline"
		
		timeframe_mapping = {"1m": "1", "5m": "5", "1h": "60", "1d": "D"}
		params = {
			"category": "spot",
			"symbol": bybit_pair,
			"interval": timeframe_mapping.get(timeframe, "1"),
			"limit": limit
		}
		raw_response = await self.network_client.fetch_json(url, params=params)
		
		if not raw_response or raw_response.get('retCode') != 0:
			return None
			
		try:
			raw_list = raw_response.get('result', {}).get('list', [])
			formatted_candles = []
			for c in reversed(raw_list):
				if len(c) >= 6:
					formatted_candles.append([
						float(c[0]), float(c[1]), float(c[2]), float(c[3]), float(c[4]), float(c[5])
					])
			return formatted_candles
		except Exception as e:
			logger.error(f"Ошибка парсинга свечей Bybit для {symbol}: {e}")
			return None

	async def fetch_balances(self) -> Dict[str, float]:
		if not self.api_key or not self.api_secret:
			return {"USDT": 0.0}
			
		url = f"{self.base_url}/v5/account/wallet-balance"
		params_str = "accountType=UNIFIED"
		url_with_params = f"{url}?{params_str}"
		
		headers = self._create_auth_headers(params_str)
		raw_response = await self.network_client.fetch_json(url_with_params, headers=headers)
		balances = {"USDT": 0.0}
		
		if not raw_response or raw_response.get('retCode') != 0:
			return balances
			
		try:
			list_data = raw_response.get('result', {}).get('list', [])
			if not list_data:
				return balances
			coins = list_data[0].get('coin', [])
			for coin_info in coins:
				coin_name = coin_info.get('coin', '').upper()
				available_balance = float(coin_info.get('availableToWithdraw', 0.0))
				balances[coin_name] = available_balance
			return balances
		except Exception as e:
			logger.error(f"Ошибка парсинга балансов Bybit: {e}")
			return balances

	async def fetch_tickers(self) -> dict:
		return {}
