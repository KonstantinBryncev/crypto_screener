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
		"""Запрос спотового стакана BingX"""
		bingx_pair = symbol.upper().replace('/', '-')
		url = f"{self.base_url}/openApi/spot/v1/market/depth"
		params = {"symbol": bingx_pair, "limit": limit}
		
		raw_response = await self.network_client.fetch_json(url, params=params)
		
		if not raw_response or 'data' not in raw_response:
			return None
			
		data = raw_response.get('data', {})
		if 'bids' not in data or 'asks' not in data:
			return None

		try:
			# ИСПРАВЛЕНО: Так как BingX отдает элементы в виде ["цена", "объем"], извлекаем item[0] и item[1]
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

	async def fetch_candles(self, symbol: str, timeframe: str = "1m", limit: int = 20) -> Optional[List[List[float]]]:
		"""Запрос спотовых исторических свечей BingX (Убрана ошибка 100400)"""
		bingx_pair = symbol.upper().replace('/', '-')
		
		# ИСПРАВЛЕНО: Использован официальный спотовый эндпоинт для графиков kline
		url = f"{self.base_url}/openApi/spot/v1/market/kline"
		
		tf_map = {"1m": "1m", "5m": "5m", "1h": "1h", "1d": "1d"}
		params = {"symbol": bingx_pair, "interval": tf_map.get(timeframe, "1m"), "limit": limit}
		
		raw_response = await self.network_client.fetch_json(url, params=params)
		if not raw_response or 'data' not in raw_response:
			return None
			
		try:
			raw_list = raw_response.get('data', [])
			formatted_candles = []
			for c in raw_list:
				if len(c) >= 6:
					# Сборка структуры спотового ответа OHLCV BingX [Timestamp, Open, High, Low, Close, Volume]
					formatted_candles.append([
						float(c[0]),  # Time
						float(c[1]),  # Open
						float(c[2]),  # High
						float(c[3]),  # Low
						float(c[4]),  # Close
						float(c[5])   # Volume
					])
			return formatted_candles
		except Exception as e:
			logger.error(f"Ошибка парсинга спотовых свечей BingX для {symbol}: {e}")
			return None

	async def fetch_balances(self) -> Dict[str, float]:
		if not self.api_key or not self.api_secret:
			return {"USDT": 0.0}
			
		url = f"{self.base_url}/openApi/spot/v1/account/balance"
		timestamp = str(int(time.time() * 1000))
		
		params_str = f"timestamp={timestamp}"
		signature = self._generate_signature(params_str)
		full_url = f"{url}?{params_str}&signature={signature}"
		
		headers = {"X-BX-APIKEY": self.api_key, "Content-Type": "application/json"}
		raw_response = await self.network_client.fetch_json(full_url, headers=headers)
		balances = {"USDT": 0.0}
		
		if not raw_response or raw_response.get('code') != 0:
			return balances
			
		try:
			data_list = raw_response.get('data', {}).get('balances', [])
			for item in data_list:
				asset_name = item.get('asset', '').upper()
				free_balance = float(item.get('free', 0.0))
				balances[asset_name] = free_balance
			return balances
		except Exception as e:
			logger.error(f"Ошибка парсинга балансов BingX: {e}")
			return balances

	async def fetch_tickers(self) -> dict:
		return {}
