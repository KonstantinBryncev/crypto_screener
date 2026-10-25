# Модуль: core/arbitrage_manager.py
import asyncio
from typing import Dict, Optional
from exchanges.bybit import BybitExchange
from exchanges.bingx import BingXExchange
from exchanges.kucoin import KuCoinExchange
from exchanges.gate import GateExchange
from core.analyzer import ArbitrageAnalyzer
import logging
from config.settings import load_bot_config  # Импортируем загрузчик

logger = logging.getLogger("ArbitrageManager")
logger.setLevel(logging.ERROR)

class ArbitrageManager:
	"""
	Специализированный менеджер ТОЛЬКО для межбиржевого арбитража.
	Опрашивает стаканы и выводит чистый спред без накопления истории в ОЗУ.
	"""
	def __init__(self):
		# 1. Загружаем настройки из файла config_bot.json
		self.bot_config = load_bot_config()
		arb_settings = self.bot_config["arbitrage"]

		self.bybit = BybitExchange()
		self.bingx = BingXExchange()
		self.kucoin = KuCoinExchange()
		self.gate = GateExchange()

		self.arbitrage_exchanges: Dict[str, object] = {
			'bybit': self.bybit,
			'bingx': self.bingx,
			'kucoin': self.kucoin,
			'gate': self.gate
		}
		
		# 2. Инициализируем анализатор
		self.arbitrage_analyzer = ArbitrageAnalyzer(min_spread_pct=arb_settings["min_spread_pct"])
		self.arbitrage_symbols = arb_settings["symbols"]
		self.network_fees = {"USDT": arb_settings["transfer_fee_usdt"]}
		
		# Читаем наш параметр базового ордера
		self.base_order_usdt = arb_settings.get("base_order_usdt", 1000)
		
		# Запоминаем задержки для циклов
		self.scan_delay = arb_settings["scan_delay_seconds"]
		self.anti_ban_delay = arb_settings["anti_ban_delay_seconds"]
		
		self.is_running: bool = False

	async def start(self):
		print("🚀 [АРБИТРАЖ] Инициализация подключения к биржам...")
		for name, ex in self.arbitrage_exchanges.items():
			try:
				# 1. Принудительно инициализируем сессию через init_exchange
				await ex.init_exchange()
				
				# 2. Жестко перебиваем настройки ccxt на спот
				if hasattr(ex, 'api') and ex.api:
					ex.api.options['defaultType'] = 'spot'
					ex.api.timeout = 20000  # Защита от медленного интернета
					
					# 3. Для Gate.io полностью пропускаем load_markets(), чтобы убрать предупреждения
					if name != 'gate':
						try:
							await ex.api.load_markets()
						except Exception as inner_e:
							print(f"⚠️ [СЕТЬ] Предупреждение для {name.upper()} при load_markets: {inner_e}")
					
				print(f"✅ Биржа {name.upper()} успешно инициализирована и готова.")
				await asyncio.sleep(2.0)  # Пауза против Rate Limit (ошибки 429)
				
			except Exception as e:
				print(f"❌ Не удалось инициализировать {name.upper()}: {e}")
				await asyncio.sleep(3.0)

		self.is_running = True
		print(f"\n⏱️ [АРБИТРАЖ] Сканер запущен (Базовый ордер: {self.base_order_usdt} USDT). Ожидание сигналов...\n")
		
		try:
			while self.is_running:
				for symbol in self.arbitrage_symbols:
					if not self.is_running:
						break
					await self._scan_arbitrage_for_symbol(symbol)
					await asyncio.sleep(self.anti_ban_delay)
				
				await asyncio.sleep(self.scan_delay)
		except asyncio.CancelledError:
			pass
		except Exception as e:
			print(f"❌ [ОШИБКА В ЦИКЛЕ АРБИТРАЖА]: {e}")
		finally:
			await self.stop()

	async def _scan_arbitrage_for_symbol(self, symbol: str):
		tasks = {}
		for name, exchange in self.arbitrage_exchanges.items():
			if hasattr(exchange, 'api') and exchange.api:
				try:
					if name == 'bybit':
						tasks[name] = asyncio.create_task(
							exchange.api.fetch_order_book(symbol, limit=5, params={
								'category': 'spot',
								'baseCoin': None
							})
						)
					elif name == 'kucoin':
						tasks[name] = asyncio.create_task(
							exchange.api.fetch_order_book(symbol, limit=20)
						)
					elif name == 'gate':
						# Переводим в btc_usdt формат для спота v4
						gate_symbol = symbol.replace('/', '_').lower()
						tasks[name] = asyncio.create_task(
							exchange.api.fetch_order_book(gate_symbol, limit=5)
						)
					elif name == 'bingx':
						tasks[name] = asyncio.create_task(
							exchange.api.fetch_order_book(symbol, limit=5)
						)
					else:
						tasks[name] = asyncio.create_task(
							exchange.api.fetch_order_book(symbol, limit=5)
						)
				except Exception:
					pass

		if not tasks:
			return

		results = await asyncio.gather(*tasks.values(), return_exceptions=True)
		
		orderbooks = {}
		for name, res in zip(tasks.keys(), results):
			# ВЫВОДИМ ДИАГНОСТИКУ ДЛЯ GATE.IO В СЫРОМ ВИДЕ:
			if name == 'gate':
				print(f"\n🔍 [ОТЛАДКА GATE] Запрашивали {symbol.replace('/', '_').lower()}")
				if isinstance(res, Exception):
					print(f"❌ [ОТЛАДКА GATE] Биржа вернула ошибку: {res}")
				elif res and isinstance(res, dict):
					print(f"✅ [ОТЛАДКА GATE] Стакан успешно получен! Асков: {len(res.get('asks', []))}, Бидов: {len(res.get('bids', []))}")
					if len(res.get('asks', [])) > 0:
						print(f"   Лучший Аск (Продажа): {res['asks'][0][0]}, Лучший Бид (Покупка): {res['bids'][0][0]}")
				else:
					print(f"⚠️ [ОТЛАДКА GATE] Неизвестный формат ответа: {res}")

			if isinstance(res, Exception):
				if "currencies" not in str(res) and "instruments-info" not in str(res):
					print(f"❌ [СЕТЬ] Ошибка получения стакана {symbol} с биржи {name.upper()}: {res}")
				continue
				
			if res and isinstance(res, dict) and 'asks' in res and 'bids' in res:
				if len(res['asks']) > 0 and len(res['bids']) > 0:
					orderbooks[name] = res

		if len(orderbooks) < 2:
			return

		for ex_a_name, ob_a in orderbooks.items():
			for ex_b_name, ob_b in orderbooks.items():
				if ex_a_name == ex_b_name:
					continue
				
				fee = self.network_fees.get("USDT", 1.0)
				
				try:
					signal = self.arbitrage_analyzer.calculate_spot_spread(
						symbol=symbol,
						exchange_a_name=ex_a_name,
						orderbook_a=ob_a,
						exchange_b_name=ex_b_name,
						orderbook_b=ob_b,
						transfer_fee=fee
					)

					if signal:
						print(f"🚨 [АРБИТРАЖНЫЙ СИГНАЛ] [{signal['symbol']}]")
						print(f"📥 Купить на {signal['buy_exchange'].upper()} по {signal['buy_price']}")
						print(f"📤 Продать на {signal['sell_exchange'].upper()} по {signal['sell_price']}")
						print(f"📊 Чистый спред: {signal['net_spread_pct']}% | Ожидаемый профит: {signal['net_profit']} USDT\n")
						
				except Exception as calc_e:
					print(f"❌ [РАСЧЕТ] Ошибка в calculate_spot_spread для {symbol}: {calc_e}")


					


	async def stop(self):
		self.is_running = False
		await asyncio.gather(*[ex.close() for ex in self.arbitrage_exchanges.values() if hasattr(ex, 'close') and ex.api])
		print("🛑 [АРБИТРАЖ] Все подключения к биржам закрыты.")
