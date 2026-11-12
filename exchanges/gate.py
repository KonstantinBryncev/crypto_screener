# Файл: exchanges/gate.py
import logging
import time
from typing import List, Optional
from exchanges.base import BaseExchange

logger = logging.getLogger("GateExchange")


class GateExchange(BaseExchange):
	"""Публичный коннектор для сканирования спотовых стаканов Gate.io (API v4)."""

	def __init__(self, network_client, base_url: str, monitored_symbols: List[str]):
		super().__init__(exchange_id="gate", base_url=base_url, monitored_symbols=monitored_symbols)
		self.network_client = network_client
		self.base_url = base_url.rstrip("/")

	async def init_exchange(self) -> bool:
		print(f"✅ [GATE.IO] Модуль успешно запущен на шлюзе: {self.base_url}", flush=True)
		return True

	async def fetch_order_book(self, symbol: str, limit: int) -> Optional[dict]:
		"""
		Запрашивает и парсит спотовый стакан Gate.io.
		Приводит уровни к числам float и гарантирует правильную сортировку.
		"""
		gate_pair = symbol.upper().replace("/", "_")
		url = f"{self.base_url}/spot/order_book"
		params = {"currency_pair": gate_pair, "limit": str(limit)}
		headers = {"Accept": "application/json"}

		try:
			raw_book = await self.network_client.fetch_json(url=url, method="GET", params=params, headers=headers)

			if not raw_book or not isinstance(raw_book, dict):
				return None

			if "bids" not in raw_book or "asks" not in raw_book:
				logger.warning(f"⚠️ [GATE.IO] Ошибка API при запросе стакана {symbol}: {raw_book}")
				return None

			parsed_asks = []
			parsed_bids = []
			idx_price = 0
			idx_amount = 1

			for item in raw_book.get("asks", []):
				if isinstance(item, list) and len(item) >= 2:
					price = float(item[idx_price])
					amount = float(item[idx_amount])
					if price > 0 and amount > 0:
						parsed_asks.append([price, amount])

			for item in raw_book.get("bids", []):
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
				"timestamp": int(time.time() * 1000),
				"type": "spot",
				"spot": True
			}
		except Exception as e:
			logger.error(f"🚨 [GATE.IO] Ошибка конвертации стакана для {symbol}: {e}")
			return None
