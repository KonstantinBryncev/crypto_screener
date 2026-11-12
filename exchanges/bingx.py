# Файл: exchanges/bingx.py
import logging
from typing import Optional, List
from exchanges.base import BaseExchange

logger = logging.getLogger("BingXExchange")


class BingXExchange(BaseExchange):
	"""Публичный коннектор для сканирования спотовых стаканов BingX."""

	def __init__(self, network_client, base_url: str, monitored_symbols: List[str]):
		super().__init__(exchange_id="bingx", base_url=base_url, monitored_symbols=monitored_symbols)
		self.network_client = network_client
		self.base_url = base_url.rstrip("/")

	async def init_exchange(self) -> bool:
		"""Штатная инициализация шлюза BingX с выводом лога в консоль."""
		print(f"✅ [BINGX Direct] Спотовое подключение запущено на хосте: {self.base_url}", flush=True)
		return True

	async def fetch_order_book(self, symbol: str, limit: int) -> Optional[dict]:
		"""
		Запрашивает и парсит стакан ордеров BingX.
		Гарантирует строгую сортировку asks по возрастанию и bids по убыванию цены.
		"""
		bingx_symbol = symbol.replace("/", "-")
		url = f"{self.base_url}/openApi/spot/v1/market/depth"
		params = {"symbol": bingx_symbol, "limit": limit}

		try:
			data = await self.network_client.fetch_json(url, method="GET", params=params)

			if not data or not isinstance(data, dict):
				return None

			if data.get("code") != 0:
				logger.warning(f"⚠️ [BINGX] Ошибка API при запросе стакана {symbol}: code={data.get('code')}, msg={data.get('msg')}")
				return None

			data_block = data.get("data", {})
			if not isinstance(data_block, dict):
				return None

			raw_asks = data_block.get("asks", [])
			raw_bids = data_block.get("bids", [])

			parsed_asks = []
			parsed_bids = []
			idx_price = 0
			idx_amount = 1

			for ask in raw_asks if isinstance(raw_asks, list) else []:
				if isinstance(ask, list) and len(ask) >= 2:
					try:
						price = float(ask[idx_price])
						amount = float(ask[idx_amount])
						if price > 0 and amount > 0:
							parsed_asks.append([price, amount])
					except (ValueError, TypeError):
						continue

			for bid in raw_bids if isinstance(raw_bids, list) else []:
				if isinstance(bid, list) and len(bid) >= 2:
					try:
						price = float(bid[idx_price])
						amount = float(bid[idx_amount])
						if price > 0 and amount > 0:
							parsed_bids.append([price, amount])
					except (ValueError, TypeError):
						continue

			if not parsed_asks or not parsed_bids:
				return None

			parsed_asks.sort(key=lambda x: x[idx_price])
			parsed_bids.sort(key=lambda x: x[idx_price], reverse=True)


			return {
				"asks": parsed_asks[:limit],
				"bids": parsed_bids[:limit],
				"symbol": symbol.upper(),
				"type": "spot",
				"spot": True
			}

		except Exception as e:
			logger.error(f"🚨 [BINGX] Критическая ошибка парсинга стакана {symbol}: {e}")
			return None
