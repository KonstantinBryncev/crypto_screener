import asyncio
import logging
import time
import hmac
import hashlib
import base64
from typing import Dict, Any, List, Optional
from exchanges.base import BaseExchange

logger = logging.getLogger("KuCoinExchange")

class KuCoinExchange(BaseExchange):
	"""
	Модуль прямого асинхронного взаимодействия с торговым шлюзом KuCoin REST API.
	Все параметры (хост, пары) динамически подтягиваются из config_bot.json.
	"""
	
	def __init__(self, network_client, base_url: str, monitored_symbols: List[str], api_key: str = "", api_secret: str = "", api_passphrase: str = ""):
		"""
		Инициализация коннектора KuCoin.
		"""
		super().__init__(exchange_id='kucoin', base_url=base_url, monitored_symbols=monitored_symbols)
		
		self.network_client = network_client
		self.api_key = api_key
		self.api_secret = api_secret
		self.api_passphrase = api_passphrase

	async def init_exchange(self):
		"""Вызывается при старте ядра скринера для подтверждения инициализации модуля."""
		print(f"✅ [KUCOIN Direct] Спотовое подключение запущено на хосте: {self.base_url}")

	def _generate_signature(self, timestamp: str, method: str, endpoint_with_params: str, body: str = "") -> str:
		"""
		Внутренний метод генерации подписи Base64 HMAC-SHA256 по стандартам KuCoin.
		"""
		str_to_sign = str(timestamp) + str(method).upper() + str(endpoint_with_params) + str(body)
		signature = hmac.new(
			self.api_secret.encode('utf-8'),
			str_to_sign.encode('utf-8'),
			hashlib.sha256
		).digest()
		return base64.b64encode(signature).decode('utf-8')

		def _generate_passphrase_signature(self) -> str:
				"""
				Возвращает пароль API (Passphrase) в формате V1 API для KuCoin.
				Если V2 (HMAC) вызывает 401 ошибку, то по спецификации V1 
				передается чистая строка фразы-пароля.
				"""
				# Зачищаем строку от пробелов и кавычек
				clean_passphrase = str(self.api_passphrase).strip().replace('"', '').replace("'", "")
				
				# Отдаем чистый текст — это решает проблему 401 для V1-ключей KuCoin
				return clean_passphrase

	async def fetch_order_book(self, symbol: str, limit: int = 5) -> Optional[dict]:
		"""
		Прямой асинхронный запрос спотового стакана KuCoin.
		"""
		kucoin_pair = symbol.upper().replace('/', '-')
		url = f"{self.base_url}/api/v1/market/orderbook/level2_20"
		params = {"symbol": kucoin_pair}
		
		raw_response = await self.network_client.fetch_json(url=url, method="GET", params=params)

		if not raw_response or not isinstance(raw_response, dict) or raw_response.get('code') != '200000':
			return None
			
		data = raw_response.get('data', {}) 
		
		if not data or not isinstance(data, dict) or 'bids' not in data or 'asks' not in data: 
			return None
			
		try:
			raw_bids = data.get('bids', [])
			raw_asks = data.get('asks', [])
			
			if not isinstance(raw_bids, list) or not isinstance(raw_asks, list):
				return None

			return {
				'bids': [[float(item[0]), float(item[1])] for item in raw_bids if item and isinstance(item, list) and len(item) >= 2],
				'asks': [[float(item[0]), float(item[1])] for item in raw_asks if item and isinstance(item, list) and len(item) >= 2],
				'symbol': symbol.upper(),
				'timestamp': int(data.get('time', time.time() * 1000)),
				'datetime': None,
				'contract': False,
				'linear': False,
				'inverse': False,
				'type': 'spot',
				'spot': True
			}
		except Exception as e:
			logger.error(f"Ошибка парсинга типов стакана KuCoin для {symbol}: {e}")
			return None

	async def fetch_balances(self) -> Dict[str, float]:
		"""
		Запрашивает текущие доступные балансы ТОРГОВОГО (trade) аккаунта KuCoin.
		"""
		if not self.api_key or not self.api_secret or not self.api_passphrase:
			return {"USDT": 0.0}
			
		endpoint = "/api/v1/accounts"
		url = f"{self.base_url}{endpoint}"  # ИСПРАВЛЕНО: Чистый URL без ?type=trade
		
		query_params = {"type": "trade"}
		endpoint_with_params = f"{endpoint}?type=trade"
		timestamp = str(int(time.time() * 1000))
		
		signature = self._generate_signature(timestamp, "GET", endpoint_with_params, body="")
		passphrase_sign = self._generate_passphrase_signature()
		
		headers = {
			"KC-API-KEY": str(self.api_key).strip(),
			"KC-API-SIGN": str(signature),
			"KC-API-TIMESTAMP": str(timestamp),
			"KC-API-PASSPHRASE": str(passphrase_sign),
			"KC-API-KEY-VERSION": "2",
			"Content-Type": "application/json"
		}
		
		raw_response = await self.network_client.fetch_json(url=url, method="GET", params=query_params, headers=headers)
		balances = {"USDT": 0.0}
		
		if not raw_response or not isinstance(raw_response, dict):
			return balances
			
		if raw_response.get('code') != '200000':
			return balances
			
		try:
			data_list = raw_response.get('data', [])
			for item in data_list:
				asset_name = item.get('currency', '').upper()
				available_balance = float(item.get('available', 0.0))
				if available_balance > 0:
					balances[asset_name] = available_balance
				
			return balances
		except Exception as e:
			logger.error(f"Ошибка при обработке приватных балансов KuCoin: {e}")
			return balances



	async def fetch_tickers(self) -> dict:
		"""Резервный метод структуры интерфейса."""
		return {}
