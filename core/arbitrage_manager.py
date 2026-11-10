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
	координирует асинхронный сбор стаканов с фильтрацией суточных объемов и запускает анализ.
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
		self.network_client = AsyncHttpClient(config)
		self.hosts = config.get("hosts", {})
		
		# Нотификаторы
		self.console_notifier = ConsoleNotifier()
		tg_config = config.get("telegram", {})
		self.tg_notifier = TelegramNotifier(
			bot_token=tg_config.get("bot_token", ""),
			chat_id=tg_config.get("chat_id", ""),
			network_client=self.network_client
		)
		
		# Инициализируем анализатор с передачей конфига для динамического DSN PostgreSQL
		self.analyzer = ArbitrageAnalyzer(config)
		self.analyzer.set_notifier(self.tg_notifier)
		
		self.monitored_symbols = []
		self.symbols_volumes = {}  # 🎯 Оперативный кэш суточных объемов торгов для записи в БД
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
		
		# ЖЕСТКИЙ АВТОЗАПУСК: Поднимаем бинарник Xray на порту 52115 перед любыми сетевыми запросами
		await self.network_client.init_tunnel()
		await asyncio.sleep(3.0)
		
		print(f"🔄 [МЕНЕДЖЕР] Собираем пары к USDT с суточным объемом торгов выше ${self.min_volume_24h:,}...")
		
		exchanges_endpoints = {
			"bybit": "/v5/market/tickers?category=spot",
			"okx": "/api/v5/market/tickers?instType=SPOT",
			"bingx": "/openApi/spot/v1/market/getTicker",
			"gate": "/api/v4/spot/tickers",
			"kucoin": "/api/v1/market/allTickers"
		}
		
		all_sets = []
		temp_volumes = {}  # Временный локальный агрегатор объемов
		
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
								pair_name = f"{base}/USDT"
								ex_pairs.add(pair_name)
								temp_volumes.setdefault(pair_name, []).append(vol)
								
				elif exchange == "okx":
					for item in data.get("data", []):
						inst_id = item.get("instId", "")
						if inst_id.endswith("-USDT"):
							vol = float(item.get("volCcy24h", 0))
							if vol >= self.min_volume_24h:
								base = inst_id.split("-")[0]
								pair_name = f"{base}/USDT"
								ex_pairs.add(pair_name)
								temp_volumes.setdefault(pair_name, []).append(vol)
								
				elif exchange == "bingx":
					tickers_list = data.get("data", [])
					if isinstance(tickers_list, list):
						for item in tickers_list:
							symbol = item.get("symbol", "")
							if symbol.endswith("-USDT"):
								vol = float(item.get("volume", 0))
								if vol >= self.min_volume_24h:
									base = symbol.split("-")[0]
									pair_name = f"{base}/USDT"
									ex_pairs.add(pair_name)
									temp_volumes.setdefault(pair_name, []).append(vol)
								
				elif exchange == "gate":
					if isinstance(data, list):
						for item in data:
							currency_pair = item.get("currency_pair", "")
							if currency_pair.endswith("_USDT"):
								vol = float(item.get("quote_volume", 0) or 0)
								if vol >= self.min_volume_24h:
									base = currency_pair.split("_")[0]
									pair_name = f"{base}/USDT"
									ex_pairs.add(pair_name)
									temp_volumes.setdefault(pair_name, []).append(vol)
									
				elif exchange == "kucoin":
					for item in data.get("data", {}).get("ticker", []):
						symbol = item.get("symbol", "")
						if symbol.endswith("-USDT"):
							vol = float(item.get("volValue", 0))
							if vol >= self.min_volume_24h:
								base = symbol.split("-")[0]
								pair_name = f"{base}/USDT"
								ex_pairs.add(pair_name)
								temp_volumes.setdefault(pair_name, []).append(vol)
				
				if ex_pairs:
					all_sets.append(ex_pairs)
					print(f"🔹 [СЕТЬ] {exchange.upper()}: Подгружено {len(ex_pairs)} ликвидных пар")
					
			except Exception as e:
				print(f"⚠️ Ошибка сбора пар с {exchange}: {e}")

		if all_sets:
			all_discovered = set.union(*all_sets)
			valid_pairs = []
			self.symbols_volumes.clear()
			
			for pair in all_discovered:
				count = sum(1 for s in all_sets if pair in s)
				if count >= 2:
					valid_pairs.append(pair)
					vols = temp_volumes.get(pair, [self.min_volume_24h])
					self.symbols_volumes[pair] = sum(vols) / len(vols)
					
			self.monitored_symbols = sorted(valid_pairs)
			print(f"✅ [МЕНЕДЖЕР] Итог: К динамическому ликвидному радару готово {len(self.monitored_symbols)} пар к USDT!")
		else:
			print("🚨 [КРИТИЧЕСКАЯ ОШИБКА СЕТИ]: Не удалось собрать общие пары. Откат на базовые маркеры.")
			self.monitored_symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
			for p in self.monitored_symbols:
				self.symbols_volumes[p] = 50000000.0

	async def start(self):
		"""Главный бесконечный цикл асинхронного сканирования рынков"""
		print("=" * 60)
		print("⚙️ [КОНФИГУРАЦИЯ] ТЕКУЩИЕ НАСТРОЙКИ РАДАРА ИЗ КФГ:")
		print(f"  🔹 Задержка сканирования:    {self.scan_delay} сек.")
		print(f"  🔹 Базовый ордер:             {self.base_volume} USDT")
		print(f"  🔹 Минимальный спред фильтра: {self.min_spread}%")
		print(f"  🔹 Максимальный спред фильтра: {self.max_spread}%")
		print(f"  🔹 Торговая комиссия (сеть):  {self.trade_fee}%")
		print(f"  🔹 Минимальный объем 24ч:     ${self.min_volume_24h:,} USDT")
		print("=" * 60)

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
			if isinstance(orderbook, Exception):
				print(f"🚨 [ОШИБКА КОДА {exch_id.upper()}]: Сбой в коннекторе для {symbol}: {orderbook}", flush=True)
				continue
				
			if orderbook and (orderbook.get("asks") or orderbook.get("bids")):
				orderbooks[exch_id] = orderbook
			else:
				# ЖЕСТКИЙ ФИКС: Переменная reason теперь гарантированно существует!
				if orderbook is None:
					reason = "Ответ пустой (None) или Cloudflare блок"
				else:
					reason = "Пустые списки asks/bids"
				print(f"⚠️ [ОТЛАДКА СТАКАНА]: Биржа {exch_id.upper()} вернула пустышку для {symbol}. Причина: {reason}", flush=True)

				
		# Если стаканы получены минимум от 2 бирж, запускаем межбиржевое сопоставление
		if len(orderbooks) >= 2:
			exch_names = list(orderbooks.keys())
			pair_volume = self.symbols_volumes.get(symbol, 0.0)
			
			for i in range(len(exch_names)):
				for j in range(i + 1, len(exch_names)):
					ex_a, ex_b = exch_names[i], exch_names[j]
					
					res = await self.analyzer.calculate_spot_spread(
						symbol=symbol, 
						exchange_a_name=ex_a, 
						orderbook_a=orderbooks[ex_a],
						exchange_b_name=ex_b, 
						orderbook_b=orderbooks[ex_b],
						volume_24h=pair_volume,
						base_volume=self.base_volume, 
						min_spread_pct=self.min_spread,
						max_spread_pct=self.max_spread, 
						trade_fee_pct=self.trade_fee
					)

					if res and isinstance(res, dict) and "spread_pct" in res:
						formatted_signal = {
							"direction": f"[{res['buy_exchange']} -> {res['sell_exchange']}]",
							"symbol": res["symbol"],
							"delta": res["spread_pct"],
							"main_metric": f"Купить: {res['buy_price']} | Продать: {res['sell_price']}",
							"volume_info": f"Объем 24ч: ${res['volume_24h']:.0f}"
						}
						self.console_notifier.print_signals([formatted_signal])
		else:
			# Если не набралось 2 живых стакана для сравнения:
			print(f"ℹ️ [ПРОПУСК {symbol}]: Живых стаканов всего {len(orderbooks)} из 5. Не с чем сопоставить.", flush=True)



	async def stop(self):
		"""Корректная остановка модулей при закрытии программы"""
		print("\n🛑 [МЕНЕДЖЕР] Инициирована остановка ядра скринера...", flush=True)
		try:
			await self.tg_notifier.send_message("⚠️ *Система межбиржевого арбитража остановлена разработчиком.*")
		except Exception:
			pass
		# ИСПРАВЛЕНО: Чистый асинхронный вызов без лишних хвостов копирования
		await self.network_client.close()
