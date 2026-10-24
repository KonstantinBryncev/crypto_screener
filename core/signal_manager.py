# Модуль: core/signal_manager.py
import asyncio
from collections import deque
from typing import Dict, List
from exchanges.bybit import BybitExchange
from exchanges.kucoin import KuCoinExchange
from core.analyzer import TickerAnalyzer
from notifications.console import ConsoleNotifier
from database.storage import CSVSignalStorage
from config import settings
import logging
from config.settings import load_bot_config  # Импортируем загрузчик

logger = logging.getLogger("SignalManager")
logger.setLevel(logging.ERROR)


class SignalManager:
	"""
	Специализированный менеджер сигналов (Памп / Дамп / Volatility).
	"""
	def __init__(self):
		# 1. Загружаем настройки из файла config_bot.json
		self.bot_config = load_bot_config()
		sig_settings = self.bot_config["signals"]

		self.bybit = BybitExchange()
		self.kucoin = KuCoinExchange()
		self.exchanges = [self.bybit, self.kucoin]
		
		# 2. Передаем параметры ИЗ ФАЙЛА НАСТРОЕК в анализатор пампов
		self.analyzer = TickerAnalyzer(
			price_change_threshold=sig_settings["price_change_threshold"], 
			volume_multiplier=sig_settings["volume_multiplier"], 
			volatility_multiplier=sig_settings["volatility_multiplier"], 
			lookback_period=sig_settings["lookback_period"]
		)
		
		self.notifier = ConsoleNotifier()
		self.storage = CSVSignalStorage()
		self.history: Dict[str, deque] = {}
		self.is_running: bool = False


	async def start(self):
		print("🚀 [СИГНАЛЫ] Инициализация подключения к биржам...")
		for ex in self.exchanges:
			try:
				await ex.init_exchange()
			except Exception:
				pass

		self.is_running = True
		print(f"\n⏱️ [СИГНАЛЫ] Скринер запущен. Интервал опроса: {settings.SCAN_INTERVAL} сек.")
		print("🎯 [КОНСОЛЬ] Вывод: ПАМПЫ, ОБЪЕМЫ, ВОЛАТИЛЬНОСТЬ")
		print("==================================================")
		
		iteration_count = 0

		try:
			while self.is_running:
				start_time = asyncio.get_event_loop().time()
				
				# Проверка баланса раз в 5 минут (30 итераций * 10 сек)
				if iteration_count % 30 == 0:
					asyncio.create_task(self._check_and_log_balance())
				
				# Собираем тикеры параллельно
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
									# Печать в консоль через стандартный нотификатор
									self.notifier.send_signal(signal)
									# Сохранение в CSV
									self.storage.add_to_save_queue(signal)
					except Exception as e:
						print(f"Ошибка сбора тикеров: {e}")
				
				iteration_count += 1
				elapsed_time = asyncio.get_event_loop().time() - start_time
				sleep_time = max(0.5, settings.SCAN_INTERVAL - elapsed_time)
				await asyncio.sleep(sleep_time)

		except asyncio.CancelledError:
			print("👋 [СИГНАЛЫ] Получен сигнал на остановку.")
		except Exception as e:
			print(f"❌ [ОШИБКА В ЦИКЛЕ СИГНАЛОВ]: {e}")
		finally:
			await self.stop()

	def _update_history(self, combined_tickers: dict):
		"""Добавление свежих тикеров в структуру хранения памяти"""
		for symbol, data in combined_tickers.items():
			if symbol not in self.history:
				self.history[symbol] = deque(maxlen=self.analyzer.lookback * 3)
			self.history[symbol].append(data)

	async def _check_and_log_balance(self):
		try:
			balance = await self.bybit.fetch_balance_usdt()
			print(f"💰 [БАЛАНС] Демо-аккаунт Bybit: {balance:,.2f} USDT")
			self.storage.add_balance_to_queue(balance)
		except Exception:
			pass

	async def stop(self):
		self.is_running = False
		await asyncio.gather(*[ex.close() for ex in self.exchanges if ex.api])
		print("🛑 [СИГНАЛЫ] Все подключения к биржам закрыты.")
