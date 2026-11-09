# Файл: exchanges/bingx.py
import logging
from typing import Optional

logger = logging.getLogger("BingXExchange")

class BingXExchange:
	"""Коннектор для работы с API биржи BingX (Spot)"""
	def __init__(self, network_client, base_url: str, monitored_symbols: list, api_key: str = "", api_secret: str = ""):
		self.network_client = network_client
		self.base_url = base_url.rstrip("/")
		self.monitored_symbols = monitored_symbols
		self.api_key = api_key
		self.api_secret = api_secret

	async def init_exchange(self):
		"""Штатная инициализация шлюза BingX"""
		return True

	async def fetch_order_book(self, symbol: str, limit: int = 5) -> Optional[dict]:
		"""
		Безопасно запрашивает и ювелирно парсит стакан ордеров BingX.
		Исключает ошибки округления цен до целых чисел.
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

			formatted_book = {"asks": [], "bids": []}

			# 🎯 ЮВЕЛИРНЫЙ ПАРСИНГ АСКОВ (Цены продажи)
			if raw_asks and isinstance(raw_asks, list):
				for ask in raw_asks[:limit]:
					if isinstance(ask, list) and len(ask) >= 2:
						try:
							# Извлекаем точную цену с точкой из первого элемента массива
							price = float(ask[0])
							formatted_book["asks"].append(price)
							break # Нам нужна только лучшая цена для расчета спреда
						except (ValueError, TypeError):
							continue

			# 🎯 ЮВЕЛИРНЫЙ ПАРСИНГ БИДОВ (Цены покупки)
			if raw_bids and isinstance(raw_bids, list):
				for bid in raw_bids[:limit]:
					if isinstance(bid, list) and len(bid) >= 2:
						try:
							# Извлекаем точную цену с точкой из первого элемента массива
							price = float(bid[0])
							formatted_book["bids"].append(price)
							break # Нам нужна только лучшая цена для расчета спреда
						except (ValueError, TypeError):
							continue

			# Возвращаем стакан, только если собрали и покупки, и продажи
			if formatted_book["asks"] and formatted_book["bids"]:
				return formatted_book
			return None

		except Exception as e:
			logger.error(f"Критическая ошибка парсинга стакана BingX для {symbol}: {e}")
			return None
