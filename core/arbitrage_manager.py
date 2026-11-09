# Файл: core/arbitrage_manager.py
import asyncio
import logging
import os
import json
import time
from typing import Dict, List

# Импорт коннекторов бирж
from exchanges.bybit import BybitExchange
from exchanges.bingx import BingXExchange
from exchanges.kucoin import KuCoinExchange
from exchanges.gate import GateExchange
from exchanges.okx import OkxExchange

# Импорт модулей анализа и сетевого клиента Reality
from core.analyzer import ArbitrageAnalyzer
from notifications.telegram import TelegramNotifier
from notifications.console import ConsoleNotifier
from network.client import AsyncHttpClient

logger = logging.getLogger("ArbitrageManager")

class ArbitrageManager:
	"""
	Ядро управления скринером. Автоматически собирает общие пары к USDT,
	координирует асинхронный сбор стаканов и запускает анализ.
	"""
	def __init__(self, config: dict):
		self.config = config
		
		# Извлекаем параметры арбитража
		arb_config = config.get("arbitrage", {})
		self.scan_delay = arb_config.get("scan_delay_seconds", 10.0)
		self.base_volume = arb_config.get("base_order_usdt", 500.0)
		self.min_spread = arb_config.get("min_spread_percent", -1.0)
		self.max_spread = arb_config.get("max_spread_percent", 50.0)
		self.trade_fee = arb_config.get("trade_fee_percent", 0.1)
		self.min_volume_24h = arb_config.get("min_volume_24h_usdt", 50000.0)
		
		# Берем синглтон HTTP-клиента с Reality-туннелем
		self.network_client = AsyncHttpClient()
		self.hosts = config.get("hosts", {})
		
		# Нотификаторы
		self.console_notifier = ConsoleNotifier()
		tg_config = config.get("telegram", {})
		self.tg_notifier = TelegramNotifier(
			bot_token=tg_config.get("bot_token", ""),
			chat_id=tg_config.get("chat_id", ""),
			network_client=self.network_client
		)
		
		# Инициализируем анализатор
		self.analyzer = ArbitrageAnalyzer()
		self.analyzer.set_notifier(self.tg_notifier)
		
		self.monitored_symbols = []
		self.exchanges = {}

	def _init_exchange_connectors(self):
		"""Внутренний метод сборки коннекторов на основе загруженного списка общих пар"""
		exch_creds = self.config.get("exchanges", {})
		exchange_mapping = {
			"bybit": BybitExchange, "bingx": BingXExchange, "kucoin": KuCoinExchange, "gate": GateExchange, "okx": OkxExchange
		}
		
		self.exchanges.clear()
		for exch_id, exch_class in exchange_mapping.items():
			host_key = f"{exch_id}_base_url"
			if host_key in self.hosts:
				creds = exch_creds.get(exch_id, {})
				kwargs = {
					"network_client": self.network_client,
					"base_url": self.hosts[host_key],
					"monitored_symbols": self.monitored_symbols,
					"api_key": creds.get("api_key", ""),
					"api_secret": creds.get("api_secret", "")
				}
				if "passphrase" in creds:
					kwargs["api_passphrase"] = creds.get("passphrase", "")
				self.exchanges[exch_id] = exch_class(**kwargs)

	async def load_all_usdt_pairs(self):
		"""Автоматический сбор общих пар к USDT с фильтрацией по минимальному суточному объему торгов"""
		print("🔄 [МЕНЕДЖЕР] Инициализация Reality-туннеля. Ожидаем 3 секунды на прогрев...")
		await asyncio.sleep(3.0)
		
		print(f"🔄 [МЕНЕДЖЕР] Собираем пары к USDT с суточным объемом торгов выше ${self.min_volume_24h:,}...")
		
		exchanges_endpoints = {
			"bybit": "/v5/market/tickers?category=spot",
			"okx": "/api/v5/market/tickers?instType=SPOT",
			"bingx": "/openApi/spot/v1/common/symbols",
			"gate": "/api/v4/spot/tickers",
			"kucoin": "/api/v1/market/allTickers"
		}
		
		all_sets = []
		
		for exchange, endpoint in exchanges_endpoints.items():
			host_key = f"{exchange}_base_url"
			if host_key not in self.hosts:
				continue
			try:
				base_url = self.hosts[host_key].rstrip("/")
				url = f"{base_url}{endpoint}"
				
				data = await self.network_client.fetch_json(url, method="GET")
				if not data:
					print(f"⚠️ [СЕТЬ] Шлюз {exchange.upper()} промолчал. Проверяем настройки.")
					continue
				
				ex_pairs = set()
				
				if exchange == "bybit":
					for item in data.get("result", {}).get("list", []):
						symbol = item.get("symbol", "")
						if symbol.endswith("USDT"):
							vol = float(item.get("volume24h", 0)) * float(item.get("lastPrice", 0))
							if vol >= self.min_volume_24h:
								base = symbol.replace("USDT", "")
								ex_pairs.add(f"{base}/USDT")
								
				elif exchange == "okx":
					for item in data.get("data", []):
						inst_id = item.get("instId", "")
						if inst_id.endswith("-USDT"):
							vol = float(item.get("volCcy24h", 0))
							if vol >= self.min_volume_24h:
								# 🛠 ТВОЙ РОДНОЙ ИСПРАВЛЕННЫЙ ИНДЕКС СЛИТА НА МЕСТЕ
								base = inst_id.split("-")[0]
								ex_pairs.add(f"{base}/USDT")
								
				elif exchange == "bingx":
					symbols_list = data.get("data", {}).get("symbols", [])
					for item in symbols_list:
						if item.get("quoteAsset") == "USDT" and item.get("status") == 1:
							base = item.get("baseAsset")
							ex_pairs.add(f"{base}/USDT")
								
				elif exchange == "gate":
					if isinstance(data, list):
						for item in data:
							currency_pair = item.get("currency_pair", "")
							if currency_pair.endswith("_USDT"):
								vol = float(item.get("quote_volume", 0))
								if vol >= self.min_volume_24h:
									base = currency_pair.split("_")[0]
									ex_pairs.add(f"{base}/USDT")
									
				elif exchange == "kucoin":
					for item in data.get("data", {}).get("ticker", []):
						symbol = item.get("symbol", "")
						if symbol.endswith("-USDT"):
							vol = float(item.get("volValue", 0))
							if vol >= self.min_volume_24h:
								base = symbol.split("-")[0]
								ex_pairs.add(f"{base}/USDT")
				
				if ex_pairs:
					all_sets.append(ex_pairs)
					print(f"🔹 [СЕТЬ] {exchange.upper()}: Подгружено {len(ex_pairs)} ликвидных пар")
					
			except Exception as e:
				print(f"⚠️ Ошибка сбора пар с {exchange}: {e}")

		if all_sets:
			all_discovered = set.union(*all_sets)
			valid_pairs = []
			for pair in all_discovered:
				count = sum(1 for s in all_sets if pair in s)
				if count >= 2:
					valid_pairs.append(pair)
					
			self.monitored_symbols = sorted(valid_pairs)
			print(f"✅ [МЕНЕДЖЕР] Итог: К динамическому ликвидному радару готово {len(self.monitored_symbols)} пар к USDT!")
		else:
			print("🚨 [КРИТИЧЕСКАЯ ОШИБКА СЕТИ]: Не удалось собрать общие пары. Откат на базовые маркеры.")
			self.monitored_symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]

	async def start(self):
		"""Главный бесконечный цикл асинхронного сканирования рынков"""
		await self.load_all_usdt_pairs()
		self._init_exchange_connectors()
		
		print("🚀 [МЕНЕДЖЕР] Асинхронный запуск всех коннекторов бирж...", flush=True)
		init_tasks = [exch.init_exchange() for exch in self.exchanges.values()]
		await asyncio.gather(*init_tasks)
		
		await self.tg_notifier.send_message(f"🔔 *Асинхронный ликвидный радар-скринер успешно запущен на {len(self.monitored_symbols)} пар к USDT!*")
		print("🟢 [МЕНЕДЖЕР] Скринер успешно начал циклическое сканирование стаканов.", flush=True)
		
		while True:
			try:
				t_start = time.time()
				batch_size = 35
				for i in range(0, len(self.monitored_symbols), batch_size):
					batch = self.monitored_symbols[i:i+batch_size]
					batch_tasks = [self._scan_single_symbol(symbol) for symbol in batch]
					await asyncio.gather(*batch_tasks)
					await asyncio.sleep(0.1)
				
				elapsed = time.time() - t_start
				sleep_time = max(0.1, self.scan_delay - elapsed)
				await asyncio.sleep(sleep_time)
			except asyncio.CancelledError:
				break
			except Exception as e:
				logger.error(f"Ошибка в цикле сканирования менеджера: {e}")
				await asyncio.sleep(5)

	async def _scan_single_symbol(self, symbol: str):
		"""Внутренний асинхронный метод сбора стаканов и расчета спреда"""
		orderbooks = {}
		tasks = {exch_id: exch_obj.fetch_order_book(symbol, limit=5) for exch_id, exch_obj in self.exchanges.items()}
		
		results = await asyncio.gather(*tasks.values(), return_exceptions=True)
		for exch_id, orderbook in zip(tasks.keys(), results):
			if orderbook and not isinstance(orderbook, Exception) and (orderbook.get("asks") or orderbook.get("bids")):
				orderbooks[exch_id] = orderbook
				
		if len(orderbooks) >= 2:
			exch_names = list(orderbooks.keys())
			for i in range(len(exch_names)):
				for j in range(i + 1, len(exch_names)):
					ex_a, ex_b = exch_names[i], exch_names[j]
					self.analyzer.calculate_spot_spread(
						symbol=symbol, exchange_a_name=ex_a, orderbook_a=orderbooks[ex_a],
						exchange_b_name=ex_b, orderbook_b=orderbooks[ex_b],
						base_volume=self.base_volume, min_spread_pct=self.min_spread,
						max_spread_pct=self.max_spread, trade_fee_pct=self.trade_fee
					)

	async def stop(self):
		"""Корректная остановка модулей при закрытии программы"""
		print("\n🛑 [МЕНЕДЖЕР] Инициирована остановка ядра скринера...", flush=True)
		try:
			await self.tg_notifier.send_message("⚠️ *Система межбиржевого арбитража остановлена разработчиком.*")
		except Exception:
			pass
		await self.network_client.close()
