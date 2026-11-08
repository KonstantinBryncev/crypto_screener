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
	Унифицированный модуль взаимодействия с REST API биржи Gate.io V4.
	"""
	def __init__(self, network_client, base_url: str, monitored_symbols: List[str], api_key: str = "", api_secret: str = ""):
		super().__init__(exchange_id='gate', base_url=base_url, monitored_symbols=monitored_symbols)
		self.network_client = network_client
		self.api_key = api_key
		self.api_secret = api_secret

	async def init_exchange(self):
		print(f"✅ [GATE.IO] Модуль успешно запущен на шлюзе: {self.base_url}")

	def _generate_sign(self, method: str, resource_path: str, query_string: str, body_str: str, timestamp: str) -> Dict[str, str]:
		"""Генерация криптографической подписи по протоколу аутентификации Gate V4 (HMAC-SHA512)"""
		hashed_body = hashlib.sha512(body_str.encode('utf-8')).hexdigest()
		signature_string = f"{method}\n{resource_path}\n{query_string}\n{hashed_body}\n{timestamp}"
		sign = hmac.new(self.api_secret.encode('utf-8'), signature_string.encode('utf-8'), hashlib.sha512).hexdigest()
		return {
			"KEY": self.api_key,
			"SIGN": sign,
			"Timestamp": timestamp,
			"Content-Type": "application/json"
		}

	async def fetch_order_book(self, symbol: str, limit: int = 5) -> Optional[dict]:
		"""Запрос текущего стакана ордеров Gate.io через маскированный сетевой клиент"""
		gate_pair = symbol.upper().replace('/', '_')
		resource_path = "/spot/order_book"
		
		# Формируем параметры запроса
		params = {"currency_pair": gate_pair, "limit": str(limit)}
		query_string = f"currency_pair={gate_pair}&limit={limit}"
		
		url = f"{self.base_url}{resource_path}"
		timestamp = str(int(time.time()))
		
		# Если ключи авторизации предоставлены — подписываем запрос, иначе отправляем чистые заголовки
		if self.api_key and self.api_secret:
			gate_headers = self._generate_sign("GET", f"/api/v4{resource_path}", query_string, body_str="", timestamp=timestamp)
		else:
			gate_headers = {"Accept": "application/json"}
		
		# Выполняем запрос через наш HttpClient
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
				'bids': [[float(item[0]), float(item[1])] for item in raw_book.get('bids', []) if item],
				'asks': [[float(item[0]), float(item[1])] for item in raw_book.get('asks', []) if item],
				'symbol': symbol.upper(),
				'timestamp': int(time.time() * 1000),
				'type': 'spot',
				'spot': True
			}
		except Exception as e:
			logger.error(f"Ошибка конвертации типов стакана Gate для {symbol}: {e}")
			return None

	async def fetch_balances(self) -> Dict[str, float]:
		"""Запрос доступных балансов спотового кошелька Gate.io"""
		if not self.api_key or not self.api_secret:
			return {"USDT": 0.0}
			
		resource_path = "/spot/accounts"
		url = f"{self.base_url}{resource_path}"
		timestamp = str(int(time.time()))
		
		headers = self._generate_sign("GET", f"/api/v4{resource_path}", "", "", timestamp)
		raw_response = await self.network_client.fetch_json(url=url, method="GET", headers=headers)
		
		balances = {"USDT": 0.0}
		if not raw_response or isinstance(raw_response, dict):
			return balances
			
		try:
			if isinstance(raw_response, list):
				for account in raw_response:
					asset_name = account.get("currency", "").upper()
					available_amount = float(account.get("available", 0.0))
					if available_amount > 0:
						balances[asset_name] = available_amount
			return balances
		except Exception as e:
			logger.error(f"Ошибка парсинга балансов Gate.io: {e}")
			return balances

	async def fetch_tickers(self) -> dict:
		return {}
