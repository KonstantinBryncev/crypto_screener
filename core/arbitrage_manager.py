# Модуль: core/arbitrage_manager.py
import asyncio
import logging
from typing import Dict, List

# Импорт коннекторов бирж
from exchanges.bybit import BybitExchange
from exchanges.bingx import BingXExchange
from exchanges.kucoin import KuCoinExchange
from exchanges.gate import GateExchange
from exchanges.okx import OkxExchange

# Импорт модулей анализа и уведомлений
from core.analyzer import ArbitrageAnalyzer
from notifications.telegram import TelegramNotifier
from notifications.console import ConsoleNotifier
from network.client import AsyncHttpClient

logger = logging.getLogger("ArbitrageManager")

class ArbitrageManager:
	"""
	Ядро управления скринером. Инициализирует биржи,
	координирует асинхронный сбор стаканов и запускает анализ.
	"""
	def __init__(self, config: dict):
		"""
		Инициализация менеджера, создание объектов бирж и анализатора.
		"""
		# Сохраняем переданный словарь конфигурации
		self.config = config
		
		# Извлекаем базовые параметры арбитража
		arb_config = config.get("arbitrage", {})
		self.monitored_symbols = arb_config.get("symbols", [])
		self.scan_delay = arb_config.get("scan_delay_seconds", 1.0)
		
		# Берем синглтон HTTP-клиента
		self.network_client = AsyncHttpClient()
		
		# Инициализируем модули вывода уведомлений
		self.console_notifier = ConsoleNotifier()
		
		tg_config = config.get("telegram", {})
		self.tg_notifier = TelegramNotifier(
			bot_token=tg_config.get("bot_token", ""),
			chat_id=tg_config.get("chat_id", ""),
			network_client=self.network_client
		)
		
		# Инициализируем математический анализатор и передаем ему нотификатор
		self.analyzer = ArbitrageAnalyzer()
		self.analyzer.set_notifier(self.tg_notifier)
		
		# Словарь для хранения активных объектов бирж
		self.exchanges = {}
		self._init_exchange_connectors()

	def _init_exchange_connectors(self):
		"""Внутренний метод сборки коннекторов на основе config_bot.json"""
		hosts = self.config.get("hosts", {})
		exch_creds = self.config.get("exchanges", {})
		
		# Список поддерживаемых бирж и их классов
		exchange_mapping = {
			"bybit": BybitExchange,
			"bingx": BingXExchange,
			"kucoin": KuCoinExchange,
			"gate": GateExchange,
			"okx": OkxExchange
		}
		
		for exch_id, exch_class in exchange_mapping.items():
			if exch_id in hosts:
				creds = exch_creds.get(exch_id, {})
				
				# Собираем базовые именованные аргументы для конструктора биржи
				kwargs = {
					"network_client": self.network_client,
					"base_url": hosts[exch_id],
					"monitored_symbols": self.monitored_symbols,
					"api_key": creds.get("api_key", ""),
					"api_secret": creds.get("api_secret", "")
				}
				
				# Добавляем специфичные параметры авторизации, если они нужны бирже
				if "passphrase" in creds:
					kwargs["api_passphrase"] = creds.get("passphrase", "")
					
				# Создаем объект коннектора
				self.exchanges[exch_id] = exch_class(**kwargs)

	async def start(self):
		"""Главный бесконечный цикл асинхронного сканирования рынков"""
		print("🚀 [МЕНЕДЖЕР] Асинхронный запуск всех коннекторов...", flush=True)
		
		# Параллельно вызываем метод init_exchange для каждой биржи
		init_tasks = [exch.init_exchange() for exch in self.exchanges.values()]
		await asyncio.gather(*init_tasks)
		
		await self.tg_notifier.send_message("🔔 *Система межбиржевого арбитража успешно запущена и ведет мониторинг!*")
		print("🟢 [МЕНЕДЖЕР] Скринер успешно начал циклическое сканирование стаканов.", flush=True)
		
		while True:
			try:
				# Перебираем все торговые пары из конфига
				for symbol in self.monitored_symbols:
					orderbooks = {}
					
					# Собираем задачи на опрос стаканов со всех бирж параллельно
					tasks = {}
					for exch_id, exch_obj in self.exchanges.items():
						tasks[exch_id] = exch_obj.fetch_order_book(symbol, limit=5)
						
					# Выполняем запросы
					results = await asyncio.gather(*tasks.values(), return_exceptions=True)
					
					# Сопоставляем результаты с ID бирж
					for exch_id, orderbook in zip(tasks.keys(), results):
						if orderbook and not isinstance(orderbook, Exception):
							orderbooks[exch_id] = orderbook
							
					# Если стаканы получены хотя бы от двух бирж — передаем их в анализатор
					if len(orderbooks) >= 2:
						# Перебираем пары бирж для поиска спреда
						exch_names = list(orderbooks.keys())
						for i in range(len(exch_names)):
							for j in range(i + 1, len(exch_names)):
								ex_a = exch_names[i]
								ex_b = exch_names[j]
								
								# Вызываем метод расчета (который мы исправили в analyzer.py)
								self.analyzer.calculate_spot_spread(
									symbol=symbol,
									exchange_a_name=ex_a,
									orderbook_a=orderbooks[ex_a],
									exchange_b_name=ex_b,
									orderbook_b=orderbooks[ex_b],
									transfer_fee=self.config.get("arbitrage", {}).get("transfer_fee_usdt", 1.5),
									base_volume=self.config.get("arbitrage", {}).get("base_order_usdt", 500.0),
									min_spread_pct=self.config.get("arbitrage", {}).get("min_spread_pct", 0.15),
									trade_fee_pct=self.config.get("arbitrage", {}).get("estimated_trade_fee_pct", 0.1),
									crypto_fees_dict=self.config.get("arbitrage", {}).get("network_fees_in_crypto", {})
								)
								
				# Задержка между итерациями общего круга сканирования
				await asyncio.sleep(self.scan_delay)
				
			except asyncio.CancelledError:
				break
			except Exception as e:
				logger.error(f"Ошибка в цикле сканирования менеджера: {e}")
				await asyncio.sleep(2)

	async def stop(self):
		"""Корректная остановка модулей при закрытии программы"""
		print("\n🛑 [МЕНЕДЖЕР] Инициирована остановка ядра скринера...", flush=True)
		try:
			await self.tg_notifier.send_message("⚠️ *Система межбиржевого арбитража остановлена разработчиком.*")
		except Exception:
			pass
		# Закрываем сессии через центральный HttpClient
		await self.network_client.close()
