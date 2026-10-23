from core.analyzer import TickerAnalyzer
from database.storage import CSVSignalStorage
import asyncio
from collections import deque
from typing import Dict, Optional
from exchanges.bybit import BybitExchange
from config import settings
from notifications.console import ConsoleNotifier


class TickerManager:
	"""
	Главный диспетчер скринера. Управляет жизненным циклом бота,
	циклами опроса биржи и хранением истории тикеров в памяти.
	"""

	def __init__(self):
		# Инициализируем наш модуль Bybit
		self.exchange = BybitExchange()
		
		# Основное хранилище истории цен и объемов.
		# Структура будет выглядеть так:
		# {
		#   'BTC/USDT': deque([{'price': 65000, 'volume': 100}, {'price': 65100, 'volume': 105}], maxlen=60),
		#   'ETH/USDT': deque([...], maxlen=60)
		# }
		self.history: Dict[str, deque] = {}
		
		# Флаг управления циклом бота
		self.is_running: bool = False

		self.analyzer = TickerAnalyzer(
			price_change_threshold=1.5, 
			volume_multiplier=3.0, 
			volatility_multiplier=4.0,  # Импульс должен быть в 4 раза сильнее среднего шума
			lookback_period=6
		)

		
		#создание нотификатора
		self.notifier = ConsoleNotifier()
		#Инициализация хранилища
		self.storage = CSVSignalStorage()





	async def start(self):
		"""Запуск бесконечного асинхронного цикла опроса биржи"""
		print("🚀 [МЕНЕДЖЕР] Инициализация подключения к бирже...")
		await self.exchange.init_exchange()
		
		self.is_running = True
		print(f"⏱️ [МЕНЕДЖЕР] Скринер запущен. Интервал опроса: {settings.SCAN_INTERVAL} сек.")

		try:
			while self.is_running:
				# Засекаем время начала цикла для точного расчета паузы
				start_time = asyncio.get_event_loop().time()
				
				# Шаг 1: Асинхронно стягиваем свежие тикеры с Bybit
				tickers = await self.exchange.fetch_tickers()

				if tickers:
					# Шаг 2: Отправляем новые данные в наше легковесное хранилище истории
					self._update_history(tickers)
					
					# Шаг 2.1: Запускаем математический анализ истории
					signals = self.analyzer.analyze(self.history)
					if signals:
						self.notifier.print_signals(signals)
						# Закидываем сигналы в безопасную асинхронную очередь
						for signal in signals:
							self.storage.add_to_save_queue(signal)


					
					# Легкий лог-счетчик для понимания, что бот жив
					print(f"📊 [МЕНЕДЖЕР] Обновлено монет в памяти: {len(tickers)}")



					

				
				# Шаг 3: Рассчитываем динамическую паузу.
				# Если запрос шел 2 секунды, а интервал у нас 10 секунд,
				# бот поспит ровно 8 секунд, чтобы циклы шли стабильно.
				elapsed_time = asyncio.get_event_loop().time() - start_time
				sleep_time = max(0.1, settings.SCAN_INTERVAL - elapsed_time)
				
				# Асинхронный сон: в этот момент скрипт полностью "отдает" процессор системе
				await asyncio.sleep(sleep_time)

		except asyncio.CancelledError:
			print("👋 [МЕНЕДЖЕР] Получен сигнал на остановку цикла.")
		finally:
			# Важно: всегда закрываем сетевые соединения при остановке
			await self.stop()

	def _update_history(self, current_tickers: Dict[str, Dict[str, float]]):
		"""
		Метод обновления истории. Добавляет новую точку в deque 
		и автоматически удаляет старые точки, если превышен лимит.
		"""
		for symbol, data in current_tickers.items():
			# Если монету видим впервые, создаем для нее персональный deque
			if symbol not in self.history:
				self.history[symbol] = deque(maxlen=settings.MAX_TIMESTAMPS)
			
			# Добавляем срез данных в очередь. 
			# Благодаря maxlen, если элементов станет больше 60, первый (самый старый) вылетит.
			self.history[symbol].append({
				'price': data['price'],
				'volume': data['volume']
			})

	async def stop(self):
		"""Корректное завершение работы менеджера"""
		self.is_running = False
		await self.exchange.close()
		print("🛑 [МЕНЕДЖЕР] Бот полностью остановлен.")

