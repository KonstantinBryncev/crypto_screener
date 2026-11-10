# Файл: exchanges/bingx.py
import logging
from typing import Optional, Dict, List
from exchanges.base import BaseExchange

logger = logging.getLogger("BingXExchange")

class BingXExchange(BaseExchange):
	"""Коннектор для работы с API биржи BingX (Spot)"""
	def __init__(self, network_client, base_url: str, monitored_symbols: List[str], api_key: str = "", api_secret: str = ""):
		# 🧬 Строгое наследование базового интерфейса радара
		super().__init__(exchange_id='bingx', base_url=base_url, monitored_symbols=monitored_symbols)
		self.network_client = network_client
		self.base_url = base_url.rstrip("/")
		self.api_key = api_key
		self.api_secret = api_secret

	async def init_exchange(self):
		"""Штатная инициализация шлюза BingX с выводом лога в консоль"""
		print(f"✅ [BINGX Direct] Спотовое подключение запущено на хосте: {self.base_url}", flush=True)
		return True

	async def fetch_order_book(self, symbol: str, limit: int = 5) -> Optional[dict]:
		"""
		Безопасно запрашивает и ювелирно парсит стакан ордеров BingX.
		Возвращает правильную вложенную структуру массивов для совместимости с анализатором.
		"""
		bingx_symbol = symbol.replace("/", "-")
		url = f"{self.base_url}/openApi/spot/v1/market/depth"
		params = {"symbol": bingx_symbol, "limit": limit}

		try:
			data = await self.network_client.fetch_json(url, method="GET", params=params)
			
			if not data or not isinstance(data, dict):
				return None

			if data.get("code") != 0:
				return None

			data_block = data.get("data", {})
			if not isinstance(data_block, dict):
				return None

			raw_asks = data_block.get("asks", [])
			raw_bids = data_block.get("bids", [])

			formatted_book = {
				"asks": [], 
				"bids": [],
				"symbol": symbol.upper(),
				"type": "spot",
				"spot": True
			}

			# 🔥 ФИКС: Убрали break, теперь стакан наполняется на всю глубину лимита!
			if raw_asks and isinstance(raw_asks, list):
				for ask in raw_asks[:limit]:
					if isinstance(ask, list) and len(ask) >= 2:
						try:
							price = float(ask[0])
							amount = float(ask[1])
							formatted_book["asks"].append([price, amount])
						except (ValueError, TypeError):
							continue

			if raw_bids and isinstance(raw_bids, list):
				for bid in raw_bids[:limit]:
					if isinstance(bid, list) and len(bid) >= 2:
						try:
							price = float(bid[0])
							amount = float(bid[1])
							formatted_book["bids"].append([price, amount])
						except (ValueError, TypeError):
							continue

			if formatted_book["asks"] and formatted_book["bids"]:
				return formatted_book
			return None

		except Exception as e:
			logger.error(f"Критическая ошибка парсинга стакана BingX для {symbol}: {e}")
			return None

	async def fetch_balances(self) -> Dict[str, float]:
		"""Резервный метод получения балансов (при необходимости реализации приватного API)"""
		return {"USDT": 0.0}

	async def fetch_tickers(self) -> dict:
		"""Резервный метод для получения тикеров"""
		return {}
