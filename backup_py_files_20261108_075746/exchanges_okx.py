import asyncio
import logging
import time
import hmac
import hashlib
import base64
import datetime
from typing import Dict, Any, List, Optional
from exchanges.base import BaseExchange

logger = logging.getLogger("OkxExchange")

class OkxExchange(BaseExchange):
	"""
	Модуль прямого асинхронного взаимодействия с торговым шлюзом OKX V5 REST API.
	Обеспечивает чтение публичных стаканов ордеров и приватных балансов спотового кошелька.
	"""
	
	def __init__(self, network_client, base_url: str, monitored_symbols: List[str], api_key: str = "", api_secret: str = "", api_passphrase: str = ""):
		"""
		Инициализация коннектора OKX с передачей параметров в абстрактный базовый класс.
		"""
		super().__init__(exchange_id='okx', base_url=base_url, monitored_symbols=monitored_symbols)
		
		self.network_client = network_client
		self.api_key = api_key
		self.api_secret = api_secret
		self.api_passphrase = api_passphrase

	async def init_exchange(self):
		"""
		Подтверждение успешной сборки и готовности модуля к работе в цикле скринера.
		"""
		print(f"✅ [OKX] Успешно инициализирован хост: {self.base_url}")

	def _generate_signature(self, timestamp: str, method: str, request_path: str, body: str = "") -> str:
		"""
		Внутренний метод сборки криптографической подписи HMAC-SHA256 Base64 по спецификации OKX V5.
		Строка для подписи склеивается БЕЗ разделителей: Таймштамп + Метод + Путь + ТелоЗапроса.
		"""
		message = timestamp + method + request_path + body
		mac = hmac.new(
			self.api_secret.encode('utf-8'),
			message.encode('utf-8'),
			hashlib.sha256
		)
		return base64.b64encode(mac.digest()).decode('utf-8')

	def _create_auth_headers(self, method: str, request_path: str, body: str = "") -> Dict[str, str]:
		"""
		Формирует валидный словарь HTTP-заголовков, необходимых для авторизации приватных эндпоинтов.
		"""
		now = datetime.datetime.now(datetime.timezone.utc)
		timestamp = now.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
		
		signature = self._generate_signature(timestamp, method, request_path, body)
		
		return {
			"OK-ACCESS-KEY": self.api_key,
			"OK-ACCESS-SIGN": signature,
			"OK-ACCESS-TIMESTAMP": timestamp,
			"OK-ACCESS-PASSPHRASE": self.api_passphrase,
			"Content-Type": "application/json"
		}

	async def fetch_order_book(self, symbol: str, limit: int = 5) -> Optional[dict]:
		"""
		Асинхронный запрос текущего спотового стакана цен с биржи OKX с защитой от сетевых сбоев.
		"""
		try:
			okx_pair = symbol.upper().replace('/', '-')
			okx_limit = limit if limit in [1, 5, 20] else 5
			resource_path = "/api/v5/market/books"
			url = f"{self.base_url}{resource_path}"
			
			params = {"instId": okx_pair, "sz": str(okx_limit)}
			
			# Переносим запрос внутрь try-except для изоляции сетевых таймаутов РФ
			raw_response = await self.network_client.fetch_json(url=url, method="GET", params=params)
			
			if not raw_response or not isinstance(raw_response, dict) or raw_response.get('code') != '0':
				return None
				
			data_list = raw_response.get('data', [])
			if not data_list or not isinstance(data_list, list):
				return None
				
			data = data_list[0]
			raw_bids = data.get('bids', [])
			raw_asks = data.get('asks', [])
			
			return {
				'bids': [[float(item[0]), float(item[1])] for item in raw_bids if item and len(item) >= 2],
				'asks': [[float(item[0]), float(item[1])] for item in raw_asks if item and len(item) >= 2],
				'symbol': symbol.upper(),
				'timestamp': int(data.get('ts', time.time() * 1000)),
				'type': 'spot',
				'spot': True
			}
		except (asyncio.TimeoutError, Exception) as e:
			# Бесшумный пропуск. Не дает скринеру зависнуть на проблемной паре из-за РКН
			logger.debug(f"Сетевой сбой OKX для {symbol}: {e}")
			return None


	async def fetch_balances(self) -> Dict[str, float]:
		"""
		Запрос доступных балансов торгового (Trading) аккаунта OKX.
		Возвращает очищенный словарь в формате {"ИмяМонеты": СвободныйОбъем}.
		"""
		if not self.api_key or not self.api_secret or not self.api_passphrase:
			return {"USDT": 0.0}
			
		resource_path = "/api/v5/account/balance"
		url = f"{self.base_url}{resource_path}"
		
		headers = self._create_auth_headers("GET", resource_path)
		raw_response = await self.network_client.fetch_json(url=url, method="GET", headers=headers)
		
		balances = {"USDT": 0.0}
		
		if not raw_response or not isinstance(raw_response, dict) or raw_response.get('code') != '0':
			return balances
			
		try:
			data_list = raw_response.get('data', [])
			if not data_list or not isinstance(data_list, list):
				return balances
				
			details = data_list[0].get('details', [])
			for coin_info in details:
				if coin_info and isinstance(coin_info, dict):
					asset_name = coin_info.get('ccy', '').upper()
					available_amount = float(coin_info.get('availBal', 0.0))
					
					if available_amount > 0:
						balances[asset_name] = available_amount
					
			return balances
		except Exception as e:
			logger.error(f"Ошибка парсинга торговых балансов OKX: {e}")
			return balances

	async def fetch_tickers(self) -> dict:
		"""Резервный метод для сохранения целостности абстрактного интерфейса BaseExchange"""
		return {}
