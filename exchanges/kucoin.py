import asyncio
import logging
import time
import hmac
import hashlib
import base64
from typing import Dict, Any, List, Optional
from exchanges.base import BaseExchange

# Настраиваем локальный логгер для модуля KuCoin
logger = logging.getLogger("KuCoinExchange")

class KuCoinExchange(BaseExchange):
	"""
	Модуль прямого асинхронного взаимодействия с торговым шлюзом KuCoin REST API.
	Все параметры (хост, пары) динамически подтягиваются из config_bot.json.
	"""
	
	# ИСПРАВЛЕНО: Явно добавлены аргументы base_url и monitored_symbols в конструктор
	def __init__(self, network_client, base_url: str, monitored_symbols: List[str], api_key: str = "", api_secret: str = "", api_passphrase: str = ""):
		"""
		Инициализация коннектора KuCoin.
		:param base_url: Базовый хост из config_bot.json
		:param monitored_symbols: Список отслеживаемых пар из config_bot.json
		:param api_passphrase: Дополнительный пароль к API (Passphrase), требуемый KuCoin.
		"""
		# Передаем конфигурационные параметры в родительский класс base.py
		super().__init__(exchange_id='kucoin', base_url=base_url, monitored_symbols=monitored_symbols)
		
		self.network_client = network_client
		self.api_key = api_key
		self.api_secret = api_secret
		self.api_passphrase = api_passphrase

	async def init_exchange(self):
		"""Вызывается при старте ядра скринера для подтверждения инициализации модуля."""
		print(f"✅ [KUCOIN Direct] Спотовое подключение запущено на хосте: {self.base_url}")


	def _generate_signature(self, timestamp: str, method: str, endpoint: str, body: str = "") -> str:
		"""
		Внутренний метод генерации подписи Base64 HMAC-SHA256 по стандартам KuCoin.
		"""
		str_to_sign = timestamp + method + endpoint + body
		signature = hmac.new(
			self.api_secret.encode('utf-8'),
			str_to_sign.encode('utf-8'),
			hashlib.sha256
		).digest()
		return base64.b64encode(signature).decode('utf-8')

	def _generate_passphrase_signature(self) -> str:
		"""
		Шифрует пароль API (Passphrase), что является обязательным требованием KuCoin.
		"""
		signature = hmac.new(
			self.api_secret.encode('utf-8'),
			self.api_passphrase.encode('utf-8'),
			hashlib.sha256
		).digest()
		return base64.b64encode(signature).decode('utf-8')

	async def fetch_order_book(self, symbol: str, limit: int = 5) -> Optional[dict]:
		"""
		Прямой асинхронный запрос спотового стакана KuCoin.
		"""
		# Формат KuCoin спот требует дефис (например, "BTC-USDT")
		kucoin_pair = symbol.upper().replace('/', '-')
		
		# Полный URL к эндпоинту частично агрегированного стакана (так быстрее и меньше весит)
		url = f"{self.base_url}/api/v1/market/orderbook/level2_20"
		params = {"symbol": kucoin_pair}
		
		# Отправляем асинхронный запрос
		raw_response = await self.network_client.fetch_json(url=url, method="GET", params=params)

		
		# Проверяем успешность ответа по внутреннему коду KuCoin (строка "200000")
		if not raw_response or raw_response.get('code') != '200000':
			return None
			
		data = raw_response.get('data', {}) # Извлекаем объект data
		if 'bids' not in data or 'asks' not in data: # Проверяем наличие массивов bids и asks
			return None
			
		try:
			# Парсим массивы цен и объемов KuCoin
			return {
				'bids': [[float(item[0]), float(item[1])] for item in data.get('bids', []) if item],
				'asks': [[float(item[0]), float(item[1])] for item in data.get('asks', []) if item],
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

	async def fetch_candles(self, symbol: str, timeframe: str = "1m", limit: int = 20) -> Optional[List[List[float]]]:
		"""
		Запрос исторических свечей KuCoin для сигнального скринера.
		"""
		kucoin_pair = symbol.upper().replace('/', '-')
		url = f"{self.base_url}/api/v1/market/candles"
		
		# Маппинг стандартных таймфреймов под кодировки KuCoin
		tf_map = {"1m": "1min", "5m": "5min", "15m": "15min", "1h": "1hour", "1d": "1day"}
		
		# Рассчитываем временные рамки, чтобы разгрузить сервер от лишних данных
		start_time = int(time.time()) - (limit * 60) # Приблизительное начало
		
		params = {
			"symbol": kucoin_pair,
			"type": tf_map.get(timeframe, "1min"),
			"startAt": start_time
		}
		
		raw_response = await self.network_client.fetch_json(url, params=params)
		if not raw_response or raw_response.get('code') != '200000':
			return None
			
		try:
			# KuCoin возвращает список: [time, open, close, high, low, volume, turnover]
			# Данные идут от новых к старым, разворачиваем reversed()
			raw_list = raw_response.get('data', [])
			
			formatted_candles = []
			for c in reversed(raw_list[:limit]):
				if len(c) >= 6:
					formatted_candles.append([
						float(c[0]) * 1000,  # Секунды в миллисекунды
						float(c[1]),         # Open
						float(c[3]),         # High (Индекс 3)
						float(c[4]),         # Low (Индекс 4)
						float(c[2]),         # Close (Индекс 2)
						float(c[5])          # Volume (Индекс 5)
					])
			return formatted_candles
		except Exception as e:
			logger.error(f"Ошибка при парсинге свечей KuCoin для {symbol}: {e}")
			return None

	async def fetch_balances(self) -> Dict[str, float]:
		"""
		Запрашивает текущие доступные балансы ТОРГОВОГО (trade) аккаунта KuCoin.
		"""
		if not self.api_key or not self.api_secret or not self.api_passphrase:
			return {"USDT": 0.0}
			
		endpoint = "/api/v1/accounts"
		# Для спотовых ордеров тип аккаунта на KuCoin называется 'trade'
		url = f"{self.base_url}{endpoint}?type=trade"
		
		timestamp = str(int(time.time() * 1000))
		# Генерируем подпись для GET-запроса (параметр '?type=trade' входит в сигнатуру)
		signature = self._generate_signature(timestamp, "GET", f"{endpoint}?type=trade")
		passphrase_sign = self._generate_passphrase_signature()
		
		headers = {
			"KC-API-KEY": self.api_key,
			"KC-API-SIGN": signature,
			"KC-API-TIMESTAMP": timestamp,
			"KC-API-PASSPHRASE": passphrase_sign,
			"KC-API-KEY-VERSION": "2",
			"Content-Type": "application/json"
		}
		
		raw_response = await self.network_client.fetch_json(url, headers=headers)
		balances = {"USDT": 0.0}
		
		if not raw_response or raw_response.get('code') != '200000':
			return balances
			
		try:
			data_list = raw_response.get('data', [])
			for item in data_list:
				asset_name = item.get('currency', '').upper()
				# available - доступно для сделок, balance - общий с учетом замороженных в ордерах
				available_balance = float(item.get('available', 0.0))
				balances[asset_name] = available_balance
				
			return balances
		except Exception as e:
			logger.error(f"Ошибка при обработке приватных балансов KuCoin: {e}")
			return balances

	async def fetch_tickers(self) -> dict:
		"""Резервный метод структуры интерфейса."""
		return {}
