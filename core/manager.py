# Модуль: core/manager.py
import asyncio
from collections import deque
from typing import Dict, List, Optional
from exchanges.bybit import BybitExchange
from exchanges.bingx import BingXExchange
from core.analyzer import TickerAnalyzer, ArbitrageAnalyzer
from notifications.console import ConsoleNotifier
from database.storage import CSVSignalStorage
from config import settings
import logging

# Выставляем логгеру уровень ERROR, чтобы варнинги сети BingX не забивали консоль
logger = logging.getLogger("TickerManager")
logger.setLevel(logging.DEBUG)

class TickerManager:
	"""
	Главный диспетчер скринера. Опрашивает биржу Bybit, контролирует таймер
	баланса демо-аккаунта (раз в 5 минут), координирует запись в ОЗУ/CSV 
	и асинхронно сканирует межбиржевой арбитраж Bybit <-> BingX.
	"""

	def __init__(self):
		# Инициализируем кастомные классы бирж
		self.bybit = BybitExchange()
		self.bingx = BingXExchange()
		
		# Пул для старого скринера пампов (пока оставляем только Bybit)
		self.exchanges = [self.bybit]
		
		# Пул бирж для арбитражного сканера (использует обе биржи)
		self.arbitrage_exchanges: Dict[str, object] = {
			'bybit': self.bybit,
			'bingx': self.bingx
		}
		
		# Математические анализаторы (Старый памп-скринер + Новый Арбитраж)
		self.analyzer = TickerAnalyzer(
			price_change_threshold=1.5, 
			volume_multiplier=3.0, 
			volatility_multiplier=4.0, 
			lookback_period=6
		)
		self.arbitrage_analyzer = ArbitrageAnalyzer(min_spread_pct=0.3)
		
		self.notifier = ConsoleNotifier()
		self.storage = CSVSignalStorage()
		
		# Валютные пары для поиска спреда между биржами
		self.arbitrage_symbols = ['BTC/USDT', 'ETH/USDT', 'LTC/USDT', 'XRP/USDT']
		# Фиксированная комиссия за вывод (1 USDT)
		self.network_fees = {"USDT": 1.0}
		
		self.history: Dict[str, deque] = {}
		self.is_running: bool = False

	async def start(self):
		"""Запуск асинхронного опроса биржи, таймера баланса и арбитражного сканера"""
		print("🚀 [МЕНЕДЖЕР] Инициализация подключения к биржам...")
		
		# Гарантированно инициализируем все биржи, которые нам нужны для арбитража
		for name, ex in self.arbitrage_exchanges.items():
			try:
				await ex.init_exchange()
			except Exception as e:
				print(f"⚠️ [ПРЕДУПРЕЖДЕНИЕ] Не удалось запустить коннектор для {name.upper()}: {e}")

		self.is_running = True
		print(f"\n⏱️ [МЕНЕДЖЕР] Скринер запущен. Интервал опроса: {settings.SCAN_INTERVAL} сек.")
		print("🎯 [КОНСОЛЬ] Вывод переключен в режим: ТОЛЬКО АРБИТРАЖ")
		print("==================================================")
		
		# Запускаем цикл арбитража как отдельную фоновую задачу
		asyncio.create_task(self._arbitrage_loop())
		
		iteration_count = 0

		try:
			# БЕЗУСЛОВНЫЙ ЦИКЛ: держит программу в памяти, пока self.is_running = True
			while self.is_running:
				start_time = asyncio.get_event_loop().time()
				
				# --- ЛОГИКА ПРОВЕРКИ БАЛАНСА (КАЖДЫЕ 5 МИНУТ) ---
				if iteration_count % 30 == 0:
					asyncio.create_task(self._check_and_log_balance())
				
				# Тихо собираем тикеры в фоне для истории пампов (только Bybit)
				fetch_tasks = []
				for ex in self.exchanges:
					if ex and ex.api:
						fetch_tasks.append(asyncio.create_task(ex.fetch_tickers()))
				
				if fetch_tasks:
					try:
						results = await asyncio.gather(*fetch_tasks, return_exceptions=True)
						combined_tickers = {}
						for exchange_tickers in results:
							if exchange_tickers and isinstance(exchange_tickers, dict):
								combined_tickers.update(exchange_tickers)
						
						if combined_tickers:
							self._update_history(combined_tickers)
							signals = self.analyzer.analyze(self.history)
							if signals:
								for signal in signals:
									self.storage.add_to_save_queue(signal)
					except Exception:
						pass # Не даем ошибкам старого скринера прервать арбитраж
				
				iteration_count += 1
				elapsed_time = asyncio.get_event_loop().time() - start_time
				
				# Расчет времени сна
				sleep_time = max(0.5, settings.SCAN_INTERVAL - elapsed_time)
				await asyncio.sleep(sleep_time)

		except asyncio.CancelledError:
			print("👋 [МЕНЕДЖЕР] Получен сигнал на остановку.")
		except Exception as e:
			# ВОТ ЗДЕСЬ ДОЛЖЕН БЫТЬ ЭТOТ БЛОК! Он поймает ошибку, если цикл старта упадет
			print(f"❌ [КРИТИЧЕСКИЙ СБОЙ ЦИКЛА]: {e}")
		finally:
			await self.stop()


	# --- ИСПРАВЛЕННАЯ ЛОГИКА МЕЖБИРЖЕВОГО АРБИТРАЖА ---

	async def _arbitrage_loop(self):
		"""Фоновый бесконечный цикл межбиржевого арбитражного сканера"""
		print("🚨 [АРБИТРАЖ] Фоновый сканер арбитражных спредов успешно запущен.")
		await asyncio.sleep(3) # Небольшая пауза перед стартом
		
		while self.is_running:
			for symbol in self.arbitrage_symbols:
				if not self.is_running:
					break
				await self._scan_arbitrage_for_symbol(symbol)
				await asyncio.sleep(0.5) # Пауза между монетами для защиты от банов по IP
			
			await asyncio.sleep(3) # Пауза перед новым кругом сравнения стаканов

	async def _scan_arbitrage_for_symbol(self, symbol: str):
		"""Параллельно собирает стаканы по одной монете со всех доступных бирж и ищет спред"""
		tasks = {}
		for name, exchange in self.arbitrage_exchanges.items():
			tasks[name] = asyncio.create_task(exchange.fetch_order_book(symbol, limit=5))
		
		results = await asyncio.gather(*tasks.values())
		orderbooks = {name: res for name, res in zip(tasks.keys(), results) if res is not None}

		for ex_a_name, ob_a in orderbooks.items():
			for ex_b_name, ob_b in orderbooks.items():
				if ex_a_name == ex_b_name:
					continue
				
				fee = self.network_fees.get("USDT", 1.0)
				
				signal = self.arbitrage_analyzer.calculate_spot_spread(
					symbol=symbol,
					exchange_a_name=ex_a_name,
					orderbook_a=ob_a,
					exchange_b_name=ex_b_name,
					orderbook_b=ob_b,
					transfer_fee=fee
				)

				if signal:
					print(f"\n🚨 [АРБИТРАЖНЫЙ СИГНАЛ] [{signal['symbol']}]")
					print(f"📥 Купить на {signal['buy_exchange'].upper()} по {signal['buy_price']}")
					print(f"📤 Продать на {signal['sell_exchange'].upper()} по {signal['sell_price']}")
					print(f"📊 Чистый спред: {signal['net_spread_pct']}% | Ожидаемый профит: {signal['net_profit']} USDT\n")

	async def _check_and_log_balance(self):
		"""Фоновый метод запроса баланса кошелька, вывода в консоль и сохранения на диск"""
		try:
			balance = await self.bybit.fetch_balance_usdt()
			if balance > 0.0 or True:
				print(f"💰 [БАЛАНС] Текущие средства на Демо-аккаунте Bybit: {balance:,.2f} USDT")
				self.storage.add_balance_to_queue(balance)
		except Exception as e:
			# Если в bybit.py нет такого метода, программа не упадет, а просто тихо скажет об этом
			print(f"⚠️ [БАЛАНС] Не удалось обновить баланс кошелька: {e}")

	async def stop(self):
		"""Корректное закрытие соединений"""
		self.is_running = False
		# Метод stop() снова чистый, он просто закрывает сессии CCXT
		await asyncio.gather(*[ex.close() for ex in self.arbitrage_exchanges.values()])
		print("🛑 [МЕНЕДЖЕР] Все подключения к биржам успешно закрыты.")
