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
		
		# Извлекаем параметры арбитража без жесткого кодирования параметров в коде
		arb_config = config.get("arbitrage", {})
		self.scan_delay = arb_config.get("scan_delay_seconds", 10.0)
		self.base_volume = arb_config.get("base_order_usdt", 500.0)
		self.min_spread = arb_config.get("min_spread_percent", -1.0)
		self.max_spread = arb_config.get("max_spread_percent", 50.0)
		self.trade_fee = arb_config.get("trade_fee_percent", 0.1)
		
		# Берем синглтон HTTP-клиента с Reality-туннелем
		self.network_client = AsyncHttpClient()
		
		# Извлекаем базовые хосты из конфигурации
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
		
		# Динамический список пар, который заполнится автоматически
		self.monitored_symbols = []
		self.exchanges = {}

	def _init_exchange_connectors(self):
		"""Внутренний метод сборки коннекторов на основе загруженного списка общих пар"""
		exch_creds = self.config.get("exchanges", {})
		
		exchange_mapping = {
			"bybit": BybitExchange,
			"bingx": BingXExchange,
			"kucoin": KuCoinExchange,
			"gate": GateExchange,
			"okx": OkxExchange
		}
		
		self.exchanges.clear()
		for exch_id, exch_class in exchange_mapping.items():
			# Сверяем с длинными ключами хостов из твоего конфига
			host_key = f"{exch_id}_base_url"
			if host_key in self.hosts:
				creds = exch_creds.get(exch_id, {})
				
				kwargs = {
					"network_client": self.network_client,
					"base_url": self.hosts[host_key],
					"monitored_symbols": self.monitored_symbols, # Передаем полный динамический список пар
					"api_key": creds.get("api_key", ""),
					"api_secret": creds.get("api_secret", "")
				}
				
				if "passphrase" in creds:
					kwargs["api_passphrase"] = creds.get("passphrase", "")
					
				self.exchanges[exch_id] = exch_class(**kwargs)

	async def load_all_usdt_pairs(self):
		"""Автоматический сбор абсолютно всех доступных пар к USDT со всех работающих шлюзов"""
		print("🔄 [МЕНЕДЖЕР] Инициализация Reality-туннеля. Ожидаем 3 секунды на прогрев...")
		await asyncio.sleep(3.0)
		
		print("🔄 [МЕНЕДЖЕР] Собираем список доступных монет к USDT через Reality-туннели...")
		
		exchanges_endpoints = {
			"bybit": "/v5/market/instruments-info?category=spot",
			"okx": "/api/v5/public/instruments?instType=SPOT",
			"bingx": "/openApi/spot/v1/common/symbols",
			"gate": "/spot/currency_pairs",
			"kucoin": "/api/v1/symbols"
		}
		
		all_sets = []
		
		for exchange, endpoint in exchanges_endpoints.items():
			# Маппинг под твои длинные ключи хостов из config_bot.json
			host_key = f"{exchange}_base_url"
			if host_key not in self.hosts:
				continue
				
			try:
				base_url = self.hosts[host_key].rstrip("/")
				if exchange == "gate":
					url = f"{base_url}/api/v4{endpoint}"
				elif "api/v4" in base_url and exchange == "gate":
					url = f"{base_url}{endpoint}"
				else:
					url = f"{base_url}{endpoint}"
				
				# Вызываем наш fetch_json синглтона через Reality-туннель
				data = await self.network_client.fetch_json(url, method="GET")
				if not data:
					print(f"⚠️ [СЕТЬ] Шлюз {exchange.upper()} промолчал. Проверяем Reality-настройки.")
					continue
				
				ex_pairs = set()
				
				if exchange == "bybit":
					for item in data.get("result", {}).get("list", []):
						if item.get("quoteCoin") == "USDT":
							ex_pairs.add(f"{item.get('baseCoin')}/USDT")
							
				elif exchange == "okx":
					for item in data.get("data", []):
						if item.get("ctValCcy") == "USDT" or item.get("instId", "").endswith("-USDT"):
							ex_pairs.add(f"{item.get('baseCcy')}/USDT")
							
				elif exchange == "bingx":
					for item in data.get("data", {}).get("symbols", []):
						if item.get("quoteAsset") == "USDT":
							ex_pairs.add(f"{item.get('baseAsset')}/USDT")
							
				elif exchange == "gate":
					if isinstance(data, list):
						for item in data:
							if item.get("quote") == "USDT" and item.get("trade_status") == "tradable":
								ex_pairs.add(f"{item.get('base')}/USDT")
							
				elif exchange == "kucoin":
					for item in data.get("data", []):
						if item.get("quoteCurrency") == "USDT" and item.get("enableTrading"):
							ex_pairs.add(f"{item.get('baseCurrency')}/USDT")
				
				if ex_pairs:
					all_sets.append(ex_pairs)
					print(f"🔹 [СЕТЬ] {exchange.upper()}: Успешно подгружено {len(ex_pairs)} пар к USDT")
					
			except Exception as e:
				print(f"⚠️ Ошибка сбора пар с {exchange}: {e}")

		if all_sets:
			all_discovered = set.union(*all_sets)
			valid_pairs = []
			for pair in all_discovered:
				count = sum(1 for s in all_sets if pair in s)
				if count >= 2: # Оставляем монеты, которые торгуются как минимум на 2 биржах из нашего списка
					valid_pairs.append(pair)
					
			self.monitored_symbols = sorted(valid_pairs)
			print(f"✅ [МЕНЕДЖЕР] Итог: К динамическому радару готово {len(self.monitored_symbols)} общих торговых пар к USDT!")
		else:
			print("🚨 [КРИТИЧЕСКАЯ ОШИБКА СЕТИ]: Не удалось собрать общие пары. Откат на базовые маркеры.")
			self.monitored_symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]

	async def start(self):
		"""Главный бесконечный цикл асинхронного сканирования рынков"""
		# 1. Сначала динамически выкачиваем сетку всех пар рынка
		await self.load_all_usdt_pairs()
		
		# 2. Инициализируем коннекторы на основе собранного списка пар
		self._init_exchange_connectors()
		
		print("🚀 [МЕНЕДЖЕР] Асинхронный запуск всех коннекторов бирж...", flush=True)
		init_tasks = [exch.init_exchange() for exch in self.exchanges.values()]
		await asyncio.gather(*init_tasks)
		
		await self.tg_notifier.send_message(f"🔔 *Асинхронный радар-скринер успешно запущен на {len(self.monitored_symbols)} пар к USDT!*")
		print("🟢 [МЕНЕДЖЕР] Скринер успешно начал циклическое сканирование стаканов.", flush=True)
		
		while True:
			try:
				t_start = time.time()
				
				# Разбиваем пары на пачки по 35 штук, чтобы асинхронность работала со свистом
				batch_size = 35
				for i in range(0, len(self.monitored_symbols), batch_size):
					batch = self.monitored_symbols[i:i+batch_size]
					
					batch_tasks = []
					for symbol in batch:
						batch_tasks.append(self._scan_single_symbol(symbol))
						
					await asyncio.gather(*batch_tasks)
					await asyncio.sleep(0.1) # Микропауза для защиты от бана по IP
				
				elapsed = time.time() - t_start
				sleep_time = max(0.1, self.scan_delay - elapsed)
				await asyncio.sleep(sleep_time)
				
			except asyncio.CancelledError:
				break
			except Exception as e:
				logger.error(f"Ошибка в цикле сканирования менеджера: {e}")
				await asyncio.sleep(5)

	async def _scan_single_symbol(self, symbol: str):
		"""Внутренний асинхронный метод сбора стаканов и расчета спреда по одной конкретной монете"""
		orderbooks = {}
		tasks = {}
		
		for exch_id, exch_obj in self.exchanges.items():
			tasks[exch_id] = exch_obj.fetch_order_book(symbol, limit=5)
			
		results = await asyncio.gather(*tasks.values(), return_exceptions=True)
		
		for exch_id, orderbook in zip(tasks.keys(), results):
			if orderbook and not isinstance(orderbook, Exception) and (orderbook.get("asks") or orderbook.get("bids")):
				orderbooks[exch_id] = orderbook
				
		if len(orderbooks) >= 2:
			exch_names = list(orderbooks.keys())
			for i in range(len(exch_names)):
				for j in range(i + 1, len(exch_names)):
					ex_a = exch_names[i]
					ex_b = exch_names[j]
					
					# 🛠 ЖЕСТКИЙ ФИЛЬТР КОНСОЛИ: вызываем калькулятор, в него уже зашит порог из конфига (self.min_spread)
					self.analyzer.calculate_spot_spread(
						symbol=symbol,
						exchange_a_name=ex_a,
						orderbook_a=orderbooks[ex_a],
						exchange_b_name=ex_b,
						orderbook_b=orderbooks[ex_b],
						base_volume=self.base_volume,
						min_spread_pct=self.min_spread,  # Сюда прилетит твои 0.5% из конфига
						max_spread_pct=self.max_spread,
						trade_fee_pct=self.trade_fee
					)

	async def stop(self):
		"""Корректная остановка модулей при закрытии программы"""
		print("\n🛑 [МЕНЕДЖЕР] Инициирована остановка ядра скринера...", flush=True)
		try:
			await self.tg_notifier.send_message("⚠️ *Система межбиржевого арбитража остановлена разработчиком.*")
		except Exception:
			pass
		await self.network_client.close()
