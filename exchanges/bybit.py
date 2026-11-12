# Файл: exchanges/bybit.py
import logging
import time
from typing import List, Optional
from exchanges.base import BaseExchange

logger = logging.getLogger("BybitExchange")


class BybitExchange(BaseExchange):
	"""Публичный коннектор для сканирования спотовых стаканов Bybit (v5)."""

	def __init__(self, network_client, base_url: str, monitored_symbols: List[str]):
		super().__init__(exchange_id="bybit", base_url=base_url, monitored_symbols=monitored_symbols)
		self.network_client = network_client
		self.base_url = base_url.rstrip("/")

	async def init_exchange(self) -> bool:
		print(f"✅ [BYBIT] Успешно инициализирован хост: {self.base_url}", flush=True)
		return True

	async def fetch_order_book(self, symbol: str, limit: int) -> Optional[dict]:
		"""
		Запрашивает и парсит спотовый стакан Bybit v5.
		Приводит уровни к числам float и гарантирует правильную сортировку.
		"""
		bybit_pair = symbol.upper().replace("/", "").replace("_", "")
		url = f"{self.base_url}/v5/market/orderbook"
		params = {"category": "spot", "symbol": bybit_pair, "limit": str(limit)}

		try:
			raw_response = await self.network_client.fetch_json(url=url, method="GET", params=params)

			if not raw_response or not isinstance(raw_response, dict):
				return None

			if raw_response.get("retCode") != 0:
				logger.warning(
					f"⚠️ [BYBIT] Ошибка API при запросе стакана {symbol}: "
					f"retCode={raw_response.get('retCode')}, retMsg={raw_response.get('retMsg')}"
				)
				return None

			result = raw_response.get("result", {})
			if "b" not in result or "a" not in result:
				return None

			parsed_asks = []
			parsed_bids = []
			idx_price = 0
			idx_amount = 1

			for item in result.get("a", []):
				if isinstance(item, list) and len(item) >= 2:
					price = float(item[idx_price])
					amount = float(item[idx_amount])
					if price > 0 and amount > 0:
						parsed_asks.append([price, amount])

			for item in result.get("b", []):
				if isinstance(item, list) and len(item) >= 2:
					price = float(item[idx_price])
					amount = float(item[idx_amount])
					if price > 0 and amount > 0:
						parsed_bids.append([price, amount])

			if not parsed_asks or not parsed_bids:
				return None

			# Сортируем asks от дешевых к дорогим, bids — от дорогих к дешевым по цене (индекс 0)
			parsed_asks.sort(key=lambda x: x[idx_price])
			parsed_bids.sort(key=lambda x: x[idx_price], reverse=True)


			return {
				"bids": parsed_bids[:limit],
				"asks": parsed_asks[:limit],
				"symbol": symbol.upper(),
				"timestamp": int(result.get("ts", time.time() * 1000)),
				"type": "spot",
				"spot": True
			}
		except Exception as e:
			logger.error(f"🚨 [BYBIT] Ошибка парсинга стакана для {symbol}: {e}")
			return None
