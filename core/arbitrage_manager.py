import asyncio
import logging
import os
import json
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
		self.config = config
		
		# Извлекаем параметры арбитража без жесткого кодирования
		arb_config = config.get("arbitrage", {})
		self.monitored_symbols = arb_config.get("symbols", ["BTC/USDT", "ETH/USDT", "SOL/USDT"])
		self.scan_delay = arb_config.get("scan_delay_seconds", 10.0)
		
		# Чтение лимитов и объемов для анализатора
		self.base_volume = arb_config.get("base_order_usdt", 500.0)
		self.min_spread = arb_config.get("min_spread_percent", -1.0)
		self.max_spread = arb_config.get("max_spread_percent", 50.0)
		self.trade_fee = arb_config.get("trade_fee_percent", 0.1)
		
		# Берем синглтон HTTP-клиента с Reality-туннелем
		self.network_client = AsyncHttpClient()
		
		# Инициализируем нотификаторы
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
		
		self.exchanges = {}
		self._init_exchange_connectors()

	def _init_exchange_connectors(self):
		"""Внутренний метод сборки коннекторов на основе config_bot.json"""
		hosts = self.config.get("hosts", {})
		exch_creds = self.config.get("exchanges", {})
		
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
				
				kwargs = {
					"network_client": self.network_client,
					"base_url": hosts[exch_id],
					"monitored_symbols": self.monitored_symbols,
					"api_key": creds.get("api_key", ""),
					"api_secret": creds.get("api_secret", "")
				}
				
				if "passphrase" in creds:
					kwargs["api_passphrase"] = creds.get("passphrase", "")
					
				self.exchanges[exch_id] = exch_class(**kwargs)

	async def start(self):
		"""Главный бесконечный цикл асинхронного сканирования рынков"""
		print("🚀 [МЕНЕДЖЕР] Асинхронный запуск всех коннекторов бирж...", flush=True)
		
		init_tasks = [exch.init_exchange() for exch in self.exchanges.values()]
		await asyncio.gather(*init_tasks)
		
		await self.tg_notifier.send_message("🔔 *Система межбиржевого арбитража успешно запущена и ведет мониторинг!*")
		print("🟢 [МЕНЕДЖЕР] Скринер успешно начал циклическое сканирование стаканов.", flush=True)
		
		while True:
			try:
				for symbol in self.monitored_symbols:
					orderbooks = {}
					tasks = {}
					
					# Опрашиваем биржи параллельно
					for exch_id, exch_obj in self.exchanges.items():
						tasks[exch_id] = exch_obj.fetch_order_book(symbol, limit=5)
						
					results = await asyncio.gather(*tasks.values(), return_exceptions=True)
					
					for exch_id, orderbook in zip(tasks.keys(), results):
						if orderbook and not isinstance(orderbook, Exception):
							orderbooks[exch_id] = orderbook
							
					# Если получили стаканы хотя бы от двух бирж — считаем спред
					if len(orderbooks) >= 2:
						exch_names = list(orderbooks.keys())
						for i in range(len(exch_names)):
							for j in range(i + 1, len(exch_names)):
								ex_a = exch_names[i]
								ex_b = exch_names[j]
								
								# Передаем параметры строго из переменных конфигурации
								self.analyzer.calculate_spot_spread(
									symbol=symbol,
									exchange_a_name=ex_a,
									orderbook_a=orderbooks[ex_a],
									exchange_b_name=ex_b,
									orderbook_b=orderbooks[ex_b],
									base_volume=self.base_volume,
									min_spread_pct=self.min_spread,
									max_spread_pct=self.max_spread,
									trade_fee_pct=self.trade_fee
								)
								
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
		await self.network_client.close()
