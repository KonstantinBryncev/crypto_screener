# Файл: exchanges/kucoin.py
import logging
import time
from typing import Optional, List
from exchanges.base import BaseExchange

logger = logging.getLogger("KuCoinExchange")


class KuCoinExchange(BaseExchange):
	"""Публичный коннектор для сканирования спотовых стаканов KuCoin."""

	def __init__(self, network_client, base_url: str, monitored_symbols: List[str]):
		super().__init__(exchange_id="kucoin", base_url=base_url, monitored_symbols=monitored_symbols)
		self.network_client = network_client
		self.base_url = base_url.rstrip("/")

	async def init_exchange(self) -> bool:
		print(f"✅ [KUCOIN] Коннектор успешно инициализирован на хосте: {self.base_url}", flush=True)
		return True

	async def fetch_order_book(self, symbol: str, limit: int) -> Optional[dict]:
		"""
		Запрашивает и парсит спотовый стакан KuCoin (level2_20).
		Приводит уровни к числам float и гарантирует правильную сортировку.
		"""
		formatted_symbol = symbol.replace("/", "-").upper()
		url = f"{self.base_url}/api/v1/market/orderbook/level2_20"
		params = {"symbol": formatted_symbol}

		try:
			raw_response = await self.network_client.fetch_json(url, method="GET", params=params)
			if not raw_response or not isinstance(raw_response, dict):
				return None

			if str(raw_response.get("code")) != "200000":
				logger.warning(
					f"⚠️ [KUCOIN] Ошибка API при запросе стакана {symbol}: "
					f"code={raw_response.get('code')}, msg={raw_response.get('msg')}"
				)
				return None

			data = raw_response.get("data")
			if not data or not isinstance(data, dict):
				return None

			raw_bids = data.get("bids")
			raw_asks = data.get("asks")
			if not isinstance(raw_bids, list) or not isinstance(raw_asks, list):
				return None

			parsed_asks = []
			parsed_bids = []
			idx_price = 0
			idx_amount = 1

			for item in raw_asks:
				if isinstance(item, list) and len(item) >= 2:
					price = float(item[idx_price])
					amount = float(item[idx_amount])
					if price > 0 and amount > 0:
						parsed_asks.append([price, amount])

			for item in raw_bids:
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
				"timestamp": int(data.get("time", time.time() * 1000)),
				"type": "spot",
				"spot": True
			}
		except Exception as e:
			logger.error(f"🚨 [KUCOIN] Ошибка парсинга стакана для {symbol}: {e}")
			return None
