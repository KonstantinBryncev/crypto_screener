# Модуль: core/manager.py
import asyncio
from collections import deque
from typing import Dict, List
from exchanges.bybit import BybitExchange
from core.analyzer import TickerAnalyzer
from notifications.console import ConsoleNotifier
from database.storage import CSVSignalStorage
from config import settings

class TickerManager:
	"""
	Главный диспетчер скринера. Опрашивает биржу Bybit, контролирует таймер
	баланса демо-аккаунта (раз в 5 минут) и координирует запись в ОЗУ/CSV.
	"""

	def __init__(self):
		self.bybit = BybitExchange()
		self.exchanges = [self.bybit]
		
		self.analyzer = TickerAnalyzer(
			price_change_threshold=1.5, 
			volume_multiplier=3.0, 
			volatility_multiplier=4.0, 
			lookback_period=6
		)
		self.notifier = ConsoleNotifier()
		self.storage = CSVSignalStorage()
		
		self.history: Dict[str, deque] = {}
		self.is_running: bool = False

	async def start(self):
		"""Запуск асинхронного опроса биржи и таймера баланса"""
		print("🚀 [МЕНЕДЖЕР] Инициализация подключения к Bybit...")
		await asyncio.gather(*[ex.init_exchange() for ex in self.exchanges])
		
		self.is_running = True
		print(f"⏱️ [МЕНЕДЖЕР] Скринер запущен. Интервал: {settings.SCAN_INTERVAL} сек.")
		
		# Счётчик итераций для отсчёта 5 минут (30 итераций по 10 секунд = 300 секунд)
		iteration_count = 0

		try:
			while self.is_running:
				start_time = asyncio.get_event_loop().time()
				
				# --- ЛОГИКА ПРОВЕРКИ БАЛАНСА (КАЖДЫЕ 5 МИНУТ) ---
				if iteration_count % 30 == 0:
					# Запускаем проверку баланса как фоновую задачу, чтобы она не тормозила сбор тикеров
					asyncio.create_task(self._check_and_log_balance())
				
				# Стандартный сбор тикеров спота
				fetch_tasks = [ex.fetch_tickers() for ex in self.exchanges]
				results: List[Dict] = await asyncio.gather(*fetch_tasks)
				
				combined_tickers = {}
				for exchange_tickers in results:
					if exchange_tickers:
						combined_tickers.update(exchange_tickers)
				
				if combined_tickers:
					self._update_history(combined_tickers)
					signals = self.analyzer.analyze(self.history)
					if signals:
						self.notifier.print_signals(signals)
						for signal in signals:
							self.storage.add_to_save_queue(signal)
					
					print(f"📊 [МЕНЕДЖЕР] Монет в мониторинге (Bybit с фильтром): {len(combined_tickers)}")
				
				iteration_count += 1
				elapsed_time = asyncio.get_event_loop().time() - start_time
				sleep_time = max(0.1, settings.SCAN_INTERVAL - elapsed_time)
				await asyncio.sleep(sleep_time)

		except asyncio.CancelledError:
			print("👋 [МЕНЕДЖЕР] Получен сигнал на остановку.")
		finally:
			await self.stop()

	async def _check_and_log_balance(self):
		"""Фоновый метод запроса баланса кошелька, вывода в консоль и сохранения на диск"""
		balance = await self.bybit.fetch_balance_usdt()
		if balance > 0.0 or True: # Условие True сработает, даже если баланс демо равен ровно 0.0
			print(f"💰 [БАЛАНС] Текущие средства на Демо-аккаунте Bybit: {balance:,.2f} USDT")
			self.storage.add_balance_to_queue(balance)

	def _update_history(self, current_tickers: Dict[str, Dict[str, float]]):
		"""Обновление скользящих окон истории цен и объемов"""
		for symbol, data in current_tickers.items():
			if symbol not in self.history:
				self.history[symbol] = deque(maxlen=settings.MAX_TIMESTAMPS)
			
			self.history[symbol].append({
				'price': data['price'],
				'volume': data['volume']
			})

	async def stop(self):
		"""Корректное закрытие соединений"""
		self.is_running = False
		await asyncio.gather(*[ex.close() for ex in self.exchanges])
		print("🛑 [МЕНЕДЖЕР] Подключение к Bybit закрыто. Бот остановлен.")
