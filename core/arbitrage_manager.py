# Файл: core/arbitrage_manager.py
import asyncio
import logging
import os
import json
import time
from typing import Dict, List

from exchanges.bybit import BybitExchange
from exchanges.bingx import BingXExchange
from exchanges.kucoin import KuCoinExchange
from exchanges.gate import GateExchange
from exchanges.okx import OkxExchange

from core.analyzer import ArbitrageAnalyzer
from network.client import AsyncHttpClient

logger = logging.getLogger("ArbitrageManager")

class ArbitrageManager:
	def __init__(self, config: dict):
		# 1. Мы сохраняем весь наш словарь CONFIG (прилетевший из main.py)
		self.config = config

		# 2. Переходим к секции 'arbitrage'. Создаем короткую переменную-ссылку (под-конфиг),
		arb_config = config.get("arbitrage", {})

		# 3. Вытаскиваем параметры из секции НАСТРОЕК ПОИСКА ВОЗМОЖНЫХ СДЕЛОК 'arbitrage' и 'network'.
		try:
			self.scan_delay = float(arb_config["scan_delay_seconds"])
			self.base_volume = float(arb_config["base_order_usdt"])
			self.min_spread = float(arb_config["min_spread_percent"])
			self.max_spread = float(arb_config["max_spread_percent"])
			self.trade_fee = float(arb_config["trade_fee_percent"])
			self.min_volume_24h = float(arb_config["min_volume_24h_usdt"])

			# Параметры главного цикла сканирования (строго из конфига, без хардкода)
			self.batch_size = int(arb_config["batch_size"])
			self.batch_timeout = float(arb_config["batch_timeout_seconds"])
			self.batch_delay = float(arb_config["batch_delay_seconds"])
			self.min_cycle_sleep = float(arb_config["min_cycle_sleep_seconds"])
			self.error_retry_delay = float(arb_config["error_retry_delay_seconds"])
			self.orderbook_limit = int(arb_config["orderbook_limit"])
			self.max_price_deviation_pct = float(self.arb_config["max_price_deviation_pct"])
			net_config = config["network"]
			self.tunnel_refresh_interval = float(net_config["tunnel_refresh_seconds"])
								#>>>>>>LET'S DEBUG<<<<<<<
			#print(f"ПЕРЕМЕННЫЕ ДЛЯ НАСТРОЙКИ ЗНАЧЕНИЙ ПОИСКА ВОЗМОЖНОЙ СДЕЛКИ:\n{json.dumps(arb_config, indent='\t', ensure_ascii=False)}")
		except KeyError as e:
			raise ValueError(f"ОШИБКА В КОНФИГЕ config/config.py: отсутствует обязательный ключ {e}")
		
		self.network_client = AsyncHttpClient(config)
								#>>>>>>LET'S DEBUG<<<<<<<
		#print(f" -> СЕТЕВЫЕ НАСТРОЙКИ:\n{json.dumps(config.get('network'), indent='\t', ensure_ascii=False)}")

		self.hosts = config.get("hosts", {})
								#>>>>>>LET'S DEBUG<<<<<<<
		#print(f" -> СПИСОК API ССЫЛОК БИРЖ:\n{json.dumps(self.hosts, indent='\t', ensure_ascii=False)}")		
		
		
		# # 9. Инициализируем математическое ядро — Анализатор.
		# # Передаем ему config, чтобы он знал параметры подключения к PostgreSQL.
		self.analyzer = ArbitrageAnalyzer(config)
		
		# # 11. Создаем пустые заготовки в памяти, которые заполнятся чуть позже:
		self.monitored_symbols = []   # тут будет чистый список общих монет (например, ['BTC/USDT', 'ETH/USDT'])
		self.symbols_volumes = {}     # тут будут храниться объемы торгов для каждой монеты
		self.exchanges = {}           # сюда запишутся готовые объекты коннекторов к биржам


	def _init_exchange_connectors(self):
		exch_creds = self.config.get("exchanges", {})
										#>>>>>>LET'S DEBUG<<<<<<<
		#print(f" -> API КЛЮЧИ ДЛЯ БИРЖ:\n{json.dumps(exch_creds, indent='\t', ensure_ascii=False)}")
		

		exchange_mapping = {
			"bybit": BybitExchange, "bingx": BingXExchange, "kucoin": KuCoinExchange, "gate": GateExchange, "okx": OkxExchange
		}
		
		self.exchanges.clear()
		for exch_id, exch_class in exchange_mapping.items():
			host_key = f"{exch_id}_base_url"
			if host_key in self.hosts:
				self.exchanges[exch_id] = exch_class(
					network_client=self.network_client,
					base_url=self.hosts[host_key],
					monitored_symbols=self.monitored_symbols,
				)


	async def load_all_usdt_pairs(self):
		# Строго требуем секцию network и ключ прогрева из config/config.py без запасных значений
		try:
			net_config = self.config["network"]
			warmup_delay = float(net_config["tunnel_warmup_seconds"])
		except KeyError as e:
			raise ValueError(f"🚨 [КОНФИГ] Отсутствует обязательный ключ в секции 'network': {e}")

		tunnel_started = await self.network_client.init_tunnel()
		if tunnel_started:
			await asyncio.sleep(warmup_delay)

		
		print(f"🔄 [МЕНЕДЖЕР] Собираем пары к USDT с суточным объемом торгов выше ${self.min_volume_24h:,}...", flush=True)
		
		exchanges_endpoints = {
			"bybit": "/v5/market/tickers?category=spot",
			"okx": "/api/v5/market/tickers?instType=SPOT",
			"bingx": f"/openApi/spot/v1/ticker/24hr?timestamp={int(time.time() * 1000)}",
			"gate": "/spot/tickers",
			"kucoin": "/api/v1/market/allTickers"
		}

		
		all_sets = []
		temp_volumes = {}
		
		for exchange, endpoint in exchanges_endpoints.items():
			host_key = f"{exchange}_base_url"
			if host_key not in self.hosts:
				print(f"⚠️ [СЕТЬ] {exchange.upper():<7}: пропущена (нет ключа '{host_key}' в config.py)", flush=True)
				continue
			try:
				base_url = self.hosts[host_key].rstrip("/")
				url = f"{base_url}{endpoint}"
				
				data = await self.network_client.fetch_json(url, method="GET")
				if not data:
					print(f"⚠️ [СЕТЬ] {exchange.upper():<7}: пустой ответ (None) от {url}", flush=True)
					continue

				
				ex_pairs = set()
				
				if exchange == "bybit":
					for item in data.get("result", {}).get("list", []):
						symbol = item.get("symbol", "")
						if symbol.endswith("USDT"):
							vol = float(item.get("volume24h", 0)) * float(item.get("lastPrice", 0))
							if vol >= self.min_volume_24h:
								pair_name = f"{symbol.replace('USDT', '')}/USDT"
								ex_pairs.add(pair_name)
								temp_volumes.setdefault(pair_name, []).append(vol)
								
				elif exchange == "okx":
					for item in data.get("data", []):
						inst_id = item.get("instId", "")
						if inst_id.endswith("-USDT"):
							vol = float(item.get("volCcy24h", 0))
							if vol >= self.min_volume_24h:
								base_coin = inst_id.split("-")[0]
								pair_name = f"{base_coin}/USDT"
								ex_pairs.add(pair_name)
								temp_volumes.setdefault(pair_name, []).append(vol)
								
				elif exchange == "bingx":
					tickers_list = data.get("data", [])
					if isinstance(tickers_list, list):
						for item in tickers_list:
							symbol = item.get("symbol", "")
							if symbol.endswith("-USDT"):
								vol = float(item.get("quoteVolume", 0) or 0)
								if vol == 0:
									last_price = float(item.get("lastPrice", 0) or 0)
									vol = float(item.get("volume", 0) or 0) * last_price
								if vol >= self.min_volume_24h:
									base_coin = symbol.split("-")[0]
									pair_name = f"{base_coin}/USDT"
									ex_pairs.add(pair_name)
									temp_volumes.setdefault(pair_name, []).append(vol)

								
				elif exchange == "gate":
					if isinstance(data, list):
						for item in data:
							currency_pair = item.get("currency_pair", "")
							if currency_pair.endswith("_USDT"):
								vol = float(item.get("quote_volume", 0) or 0)
								if vol >= self.min_volume_24h:
									base_coin = currency_pair.split("_")[0]
									pair_name = f"{base_coin.upper()}/USDT"
									ex_pairs.add(pair_name)
									temp_volumes.setdefault(pair_name, []).append(vol)
									
				elif exchange == "kucoin":
					for item in data.get("data", {}).get("ticker", []):
						symbol = item.get("symbol", "")
						if symbol.endswith("-USDT"):
							vol = float(item.get("volValue", 0))
							if vol >= self.min_volume_24h:
								base_coin = symbol.split("-")[0]
								pair_name = f"{base_coin}/USDT"
								ex_pairs.add(pair_name)
								temp_volumes.setdefault(pair_name, []).append(vol)
				
				if ex_pairs:
					all_sets.append(ex_pairs)
					print(f"🔹 [СЕТЬ] {exchange.upper():<7}: УСПЕШНО подгружено {len(ex_pairs)} пар", flush=True)
				else:
					# Выводим сырой фрагмент ответа, чтобы сразу видеть, почему 0 пар
					sample = str(data)[:140] if data else "Пустой ответ (None)"
					print(f"⚠️ [СЕТЬ] {exchange.upper():<7}: 0 пар прошло фильтр | Ответ API: {sample}", flush=True)
					
			except Exception as ex_err:
				logger.error(f"🚨 [СЕТЬ] Ошибка парсинга тикеров {exchange.upper()}: {ex_err}")
				print(f"🚨 [СЕТЬ] {exchange.upper():<7}: ОШИБКА ({ex_err})", flush=True)

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
			print("-" * 65, flush=True)
			print(f"✅ [МЕНЕДЖЕР] Итог пересечения: к арбитражу готово {len(self.monitored_symbols)} общих пар (минимум на 2 биржах)!", flush=True)
			print("-" * 65 + "\n", flush=True)




	async def start(self):
		print("\n" + "=" * 65, flush=True)
		print("🚀 СУПЕР-СКАНЕР ЗАПУЩЕН | АКТИВНЫЕ НАСТРОЙКИ ИЗ CONFIG.PY:", flush=True)
		print("=" * 65, flush=True)
		print(f"   • Коридор чистого спреда : от {self.min_spread}% до {self.max_spread}%", flush=True)
		print(f"   • Рабочий объем ордера   : ${self.base_volume:,.2f} USDT", flush=True)
		print(f"   • Комиссия биржи (1 круг): {self.trade_fee}% (итого {self.trade_fee * 2:.2f}%)", flush=True)
		print(f"   • Мин. объем пары за 24ч : ${self.min_volume_24h:,.0f} USDT", flush=True)
		print(f"   • Глубина стакана (VWAP) : {self.orderbook_limit} уровней", flush=True)
		print(f"   • Батчинг и таймауты     : пачка {self.batch_size} пар | таймаут {self.batch_timeout}с | пауза {self.batch_delay}с", flush=True)
		print(f"   • Пауза полного цикла    : {self.scan_delay}с (мин. {self.min_cycle_sleep}с)", flush=True)
		print("=" * 65 + "\n", flush=True)


		await self.load_all_usdt_pairs()
		self._init_exchange_connectors()
		
		init_tasks = [exch.init_exchange() for exch in self.exchanges.values()]
		await asyncio.gather(*init_tasks)
		
		last_tunnel_refresh = time.time()
		
		while True:
			try:
				if time.time() - last_tunnel_refresh > self.tunnel_refresh_interval:
					print("🔄 [МЕНЕДЖЕР] Прошло 4 часа. Автоматическое обновление туннеля Reality...")
					await self.network_client.init_tunnel()
					last_tunnel_refresh = time.time()
					
				t_start = time.time()
				for i in range(0, len(self.monitored_symbols), self.batch_size):
					batch = self.monitored_symbols[i:i+self.batch_size]
					batch_tasks = [self._scan_single_symbol(symbol) for symbol in batch]
					
					# 🎯 СВЕРХНАДЕЖНОСТЬ: Ограничиваем обработку пачки батчей таймаутом из конфига
					try:
						await asyncio.wait_for(asyncio.gather(*batch_tasks), timeout=self.batch_timeout)
					except asyncio.TimeoutError:
						pass
					await asyncio.sleep(self.batch_delay)
				
				elapsed = time.time() - t_start
				sleep_time = max(self.min_cycle_sleep, self.scan_delay - elapsed)
				await asyncio.sleep(sleep_time)
			except Exception as loop_err:
				logger.error(f"🚨 [ЦИКЛ] Ошибка в главном цикле start(): {loop_err}")
				await asyncio.sleep(self.error_retry_delay)


	async def _scan_single_symbol(self, symbol: str):
		try:
			orderbooks = {}
			# Берем глубину стакана строго из self.orderbook_limit (загружено из config/config.py)
			tasks = {
				exch_id: exch_obj.fetch_order_book(symbol, limit=self.orderbook_limit)
				for exch_id, exch_obj in self.exchanges.items()
			}
			results = await asyncio.gather(*tasks.values(), return_exceptions=True)

			for exch_id, orderbook in zip(tasks.keys(), results):
				if isinstance(orderbook, Exception):
					continue
				# Проверяем, что в стакане есть обе стороны (asks и bids)
				if orderbook and orderbook.get("asks") and orderbook.get("bids"):
					orderbooks[exch_id] = orderbook

			# Отсекаем биржи с зависшими ценами / закрытыми кошельками по отклонению от медианы рынка
			if len(orderbooks) >= 3:
				mid_prices = {}
				idx = 0
				for ex_name, ob in orderbooks.items():
					best_ask = ob["asks"][idx][idx]
					best_bid = ob["bids"][idx][idx]
					mid_prices[ex_name] = (best_ask + best_bid) / 2.0

				sorted_prices = sorted(mid_prices.values())
				median_price = sorted_prices[len(sorted_prices) // 2]

				filtered_orderbooks = {}
				for ex_name, ob in orderbooks.items():
					dev_pct = abs(mid_prices[ex_name] - median_price) / median_price * 100.0
					if dev_pct <= self.max_price_deviation_pct:
						filtered_orderbooks[ex_name] = ob

				orderbooks = filtered_orderbooks

			if len(orderbooks) < 2:
				return

			exch_names = list(orderbooks.keys())
			pair_volume = self.symbols_volumes.get(symbol, 0.0)

			for i in range(len(exch_names)):
				for j in range(i + 1, len(exch_names)):
					ex_a, ex_b = exch_names[i], exch_names[j]

					# Запускаем расчет математического спреда по глубине стакана
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
						# Прямой вывод сигнала в консоль
						print("\n" + "🔥" * 20, flush=True)
						print(f"🚨 [АРБИТРАЖНЫЙ СИГНАЛ] Найдена связка!", flush=True)
						print(f"   -> Монета: {res['symbol']}", flush=True)
						print(f"   -> Направление: [{res['buy_exchange'].upper()} -> {res['sell_exchange'].upper()}]", flush=True)
						print(f"   -> Спред: {res['spread_pct']}%", flush=True)
						print(f"   -> Математика: Купить по {res['buy_price']:.8g} | Продать по {res['sell_price']:.8g}", flush=True)
						print(f"   -> Суточный объем: ${pair_volume:.0f} | Объем сделки: ${self.base_volume}", flush=True)
						print("=" * 40 + "\n", flush=True)

		except Exception as scan_err:
			# Фиксируем любую ошибку при сканировании монеты в bot_errors.log вместо молчаливого pass
			logger.error(f"🚨 [СКАНЕР] Ошибка при сканировании монеты {symbol}: {scan_err}")

	async def stop(self):
		print("\n🛑 [МЕНЕДЖЕР] Остановка сканера и закрытие сетевого туннеля...", flush=True)
		await self.network_client.close()
