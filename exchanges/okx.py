# Файл: exchanges/okx.py
import logging
import time
from typing import List, Optional
from exchanges.base import BaseExchange

logger = logging.getLogger("OkxExchange")


class OkxExchange(BaseExchange):
	"""Публичный коннектор для сканирования спотовых стаканов OKX (API v5)."""

	def __init__(self, network_client, base_url: str, monitored_symbols: List[str]):
		super().__init__(exchange_id="okx", base_url=base_url, monitored_symbols=monitored_symbols)
		self.network_client = network_client
		self.base_url = base_url.rstrip("/")

	async def init_exchange(self) -> bool:
		print(f"✅ [OKX] Успешно инициализирован хост: {self.base_url}", flush=True)
		return True

	async def fetch_order_book(self, symbol: str, limit: int) -> Optional[dict]:
		"""
		Запрашивает и парсит спотовый стакан OKX v5.
		Приводит уровни к числам float и гарантирует правильную сортировку.
		"""
		okx_pair = symbol.upper().replace("/", "-")
		url = f"{self.base_url}/api/v5/market/books"
		params = {"instId": okx_pair, "sz": str(limit)}

		try:
			raw_response = await self.network_client.fetch_json(url=url, method="GET", params=params)

			if not raw_response or not isinstance(raw_response, dict):
				return None

			if str(raw_response.get("code")) != "0":
				logger.warning(
					f"⚠️ [OKX] Ошибка API при запросе стакана {symbol}: "
					f"code={raw_response.get('code')}, msg={raw_response.get('msg')}"
				)
				return None

			data_list = raw_response.get("data", [])
			if not data_list or not isinstance(data_list, list):
				return None

			idx_first = 0
			idx_price = 0
			idx_amount = 1
			data = data_list[idx_first]

			parsed_asks = []
			parsed_bids = []

			for item in data.get("asks", []):
				if isinstance(item, list) and len(item) >= 2:
					price = float(item[idx_price])
					amount = float(item[idx_amount])
					if price > 0 and amount > 0:
						parsed_asks.append([price, amount])

			for item in data.get("bids", []):
				if isinstance(item, list) and len(item) >= 2:
					price = float(item[idx_price])
					amount = float(item[idx_amount])
					if price > 0 and amount > 0:
						parsed_bids.append([price, amount])

			if not parsed_asks or not parsed_bids:
				return None

			# Сортируем asks от дешевых к дорогим, bids — от дорогих к дешевым
			parsed_asks.sort(key=lambda x: x[idx_price])
			parsed_bids.sort(key=lambda x: x[idx_price], reverse=True)

			return {
				"bids": parsed_bids[:limit],
				"asks": parsed_asks[:limit],
				"symbol": symbol.upper(),
				"timestamp": int(data.get("ts", time.time() * 1000)),
				"type": "spot",
				"spot": True
			}
		except Exception as e:
			logger.error(f"🚨 [OKX] Ошибка парсинга стакана для {symbol}: {e}")
			return None
