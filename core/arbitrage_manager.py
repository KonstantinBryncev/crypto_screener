# Модуль: core/arbitrage_manager.py
import asyncio
from typing import Dict, Optional
from exchanges.bybit import BybitExchange
from exchanges.bingx import BingXExchange
from exchanges.kucoin import KuCoinExchange
from core.analyzer import ArbitrageAnalyzer
from config import settings
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

		self.arbitrage_exchanges: Dict[str, object] = {
			'bybit': self.bybit,
			'bingx': self.bingx,
			'kucoin': self.kucoin
		}
		
		# 2. Передаем параметры ИЗ ФАЙЛА НАСТРОЕК в анализатор и менеджер
		self.arbitrage_analyzer = ArbitrageAnalyzer(min_spread_pct=arb_settings["min_spread_pct"])
		self.arbitrage_symbols = arb_settings["symbols"]
		self.network_fees = {"USDT": arb_settings["transfer_fee_usdt"]}
		
		# Запоминаем задержки для циклов
		self.scan_delay = arb_settings["scan_delay_seconds"]
		self.anti_ban_delay = arb_settings["anti_ban_delay_seconds"]
		
		self.is_running: bool = False

	async def start(self):
		print("🚀 [АРБИТРАЖ] Инициализация подключения к биржам...")
		for name, ex in self.arbitrage_exchanges.items():
			try:
				await ex.init_exchange()
			except Exception:
				pass

			# Находим метод start и меняем блок цикла while на этот:
	async def start(self):
		# ... (код инициализации бирж остается прежним) ...
		self.is_running = True
		print(f"\n⏱️ [АРБИТРАЖ] Сканер запущен. Пауза между кругами: {self.scan_delay} сек.")
		print("==================================================")
		
		try:
			while self.is_running:
				for symbol in self.arbitrage_symbols:
					if not self.is_running:
						break
					await self._scan_arbitrage_for_symbol(symbol)
					await asyncio.sleep(self.anti_ban_delay) # Используем настройку из файла
				
				await asyncio.sleep(self.scan_delay) # Используем настройку из файла
		# ... (остальной код try/except/finally остается прежним) ...


		except asyncio.CancelledError:
			print("👋 [АРБИТРАЖ] Получен signal на остановку.")
		except Exception as e:
			print(f"❌ [ОШИБКА В ЦИКЛЕ АРБИТРАЖА]: {e}")
		finally:
			await self.stop()

	async def _scan_arbitrage_for_symbol(self, symbol: str):
		tasks = {}
		for name, exchange in self.arbitrage_exchanges.items():
			if exchange.api:
				tasks[name] = asyncio.create_task(
					exchange.api.fetch_order_book(symbol, limit=5, params={'category': 'spot'})
				)
		
		if not tasks:
			return

		results = await asyncio.gather(*tasks.values(), return_exceptions=True)
		
		orderbooks = {}
		for name, res in zip(tasks.keys(), results):
			if res and isinstance(res, dict) and 'asks' in res and 'bids' in res:
				orderbooks[name] = res

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
					print(f"🚨 [АРБИТРАЖНЫЙ СИГНАЛ] [{signal['symbol']}]")
					print(f"📥 Купить на {signal['buy_exchange'].upper()} по {signal['buy_price']}")
					print(f"📤 Продать на {signal['sell_exchange'].upper()} по {signal['sell_price']}")
					print(f"📊 Чистый спред: {signal['net_spread_pct']}% | Ожидаемый профит: {signal['net_profit']} USDT\n")

	async def stop(self):
		self.is_running = False
		await asyncio.gather(*[ex.close() for ex in self.arbitrage_exchanges.values() if ex.api])
		print("🛑 [АРБИТРАЖ] Все подключения к биржам закрыты.")
