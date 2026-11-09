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
		Безопасно запрашивает и парсит стакан ордеров BingX.
		Устойчив к текстовым ошибкам API и делистингам.
		"""
		# Превращаем формат пары под стандарт BingX (например, ATOM/USDT -> ATOM-USDT)
		bingx_symbol = symbol.replace("/", "-")
		url = f"{self.base_url}/openApi/spot/v1/market/depth"
		params = {"symbol": bingx_symbol, "limit": limit}

		try:
			data = await self.network_client.fetch_json(url, method="GET", params=params)
			
			# 🎯 ЖЕЛЕЗНЫЙ ФИЛЬТР: Если биржа вернула строку вместо словаря — мягко выходим
			if not data or not isinstance(data, dict):
				return None

			# Проверяем внутренний код ответа биржи
			if data.get("code") != 0:
				return None

			data_block = data.get("data", {})
			if not isinstance(data_block, dict):
				return None

			asks = data_block.get("asks", [])
			bids = data_block.get("bids", [])

			# Форматируем стакан под единый стандарт нашего анализатора
			formatted_book = {"asks": [], "bids": []}

			if asks and len(asks) > 0:
				# Сохраняем лучшую цену продажи (Ask)
				formatted_book["asks"] = asks[0][0]

			if bids and len(bids) > 0:
				# Сохраняем лучшую цену покупки (Bid)
				formatted_book["bids"] = bids[0][0]

			return formatted_book

		except Exception as e:
			# Мягко логируем только критические системные сбои, игнорируя делистинги щиткоинов
			return None
