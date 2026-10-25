import asyncio
import json
import os
import time
from pathlib import Path
from core.analyzer import ArbitrageAnalyzer
from network.client import AsyncHttpClient

# Импорт конкретных коннекторов бирж
from exchanges.bybit import BybitExchange
from exchanges.bingx import BingXExchange
from exchanges.kucoin import KuCoinExchange
from exchanges.gate import GateExchange

class ArbitrageManager:
	"""
	Главный координатор скринера. Динамически собирает инстансы бирж
	из config_bot.json и управляет асинхронным циклом межбиржевого сканирования.
	"""
	def __init__(self):
		self.arbitrage_analyzer = ArbitrageAnalyzer()
		self.network_client = AsyncHttpClient()
		self.is_running = False
		
		# Загрузка центрального файла конфигурации
		self.config = self._load_config()
		
		# Вычисляем корень проекта для динамической сборки путей
		current_dir = os.path.dirname(os.path.abspath(__file__))
		self.project_root = Path(os.path.dirname(current_dir))
		
		# Извлекаем именованные блоки параметров из JSON
		hosts_settings = self.config.get("hosts", {})
		exchanges_settings = self.config.get("exchanges", {})
		arb_settings = self.config.get("arbitrage", {})
		system_settings = self.config.get("system", {})
		
		# Распределяем параметры алгоритма по внутренним переменным
		self.monitored_symbols = arb_settings.get("symbols", [])
		self.base_order_usdt = float(arb_settings.get("base_order_usdt", 1000.0))
		self.transfer_fee_usdt = float(arb_settings.get("transfer_fee_usdt", 1.0))
		self.scan_delay_seconds = float(arb_settings.get("scan_delay_seconds", 3.0))
		self.min_spread_pct = float(arb_settings.get("min_spread_pct", 0.5))
		self.estimated_trade_fee_pct = float(arb_settings.get("estimated_trade_fee_pct", 0.1))
		self.anti_ban_delay_seconds = float(arb_settings.get("anti_ban_delay_seconds", 0.5))

		# Инициализируем системные лимиты
		self.max_timestamps = int(system_settings.get("max_timestamps", 60))
		self.min_24h_volume = float(system_settings.get("min_24h_volume_usdt", 50000.0))

		# Глобальный пул объектов коннекторов бирж
		self.exchanges = {
			"bybit": BybitExchange(
				network_client=self.network_client,
				base_url=str(hosts_settings.get("bybit")),
				monitored_symbols=self.monitored_symbols,
				api_key=exchanges_settings.get("bybit", {}).get("api_key", ""),
				api_secret=exchanges_settings.get("bybit", {}).get("api_secret", "")
			),
			"bingx": BingXExchange(
				network_client=self.network_client,
				base_url=str(hosts_settings.get("bingx")),
				monitored_symbols=self.monitored_symbols,
				api_key=exchanges_settings.get("bingx", {}).get("api_key", ""),
				api_secret=exchanges_settings.get("bingx", {}).get("api_secret", "")
			),
			"kucoin": KuCoinExchange(
				network_client=self.network_client,
				base_url=str(hosts_settings.get("kucoin")),
				monitored_symbols=self.monitored_symbols,
				api_key=exchanges_settings.get("kucoin", {}).get("api_key", ""),
				api_secret=exchanges_settings.get("kucoin", {}).get("api_secret", ""),
				api_passphrase=exchanges_settings.get("kucoin", {}).get("passphrase", "")
			),
			"gate": GateExchange(
				network_client=self.network_client,
				base_url=str(hosts_settings.get("gate")),
				monitored_symbols=self.monitored_symbols,
				api_key=exchanges_settings.get("gate", {}).get("api_key", ""),
				api_secret=exchanges_settings.get("gate", {}).get("api_secret", "")
			)
		}

	def _load_config(self) -> dict:
		"""Вспомогательный метод для чтения config_bot.json из корня проекта"""
		current_dir = os.path.dirname(os.path.abspath(__file__))
		project_root = os.path.dirname(current_dir)
		config_path = os.path.join(project_root, "config_bot.json")
		
		if os.path.exists(config_path):
			try:
				with open(config_path, "r", encoding="utf-8") as f:
					return json.load(f)
			except Exception as e:
				print(f"⚠️ Ошибка чтения config_bot.json: {e}")
		return {}

	async def init_all_exchanges(self):
		"""Вызывает лог готовности для каждого коннектора"""
		for ex_name, ex_instance in self.exchanges.items():
			await ex_instance.init_exchange()
		print("==================================================")
		print("✅ [АРБИТРАЖ REST] Все авторизованные API-шлюзы успешно инициализированы.")

	async def _scan_arbitrage_for_symbol(self, symbol: str):
		"""Последовательный опрос торговых шлюзов бирж и запуск калькуляции спредов."""
		orderbooks = {}
		
		# Опрашиваем каждую биржу из нашего пула
		for ex_name, ex_instance in self.exchanges.items():
			try:
				ob = await ex_instance.fetch_order_book(symbol)
				if ob and ob.get('bids') and ob.get('asks'):
					orderbooks[ex_name] = ob
			except Exception as e:
				print(f"⚠️ Ошибка сбора стакана с биржи {ex_name} для {symbol}: {e}")
			
			# Пауза для защиты от Rate Limit (Rate limit / Cloudflare)
			await asyncio.sleep(self.anti_ban_delay_seconds)
		
		# Если стаканы ответили меньше чем от 2 бирж — арбитраж невозможен
		if len(orderbooks) < 2:
			return

		# ИСПРАВЛЕНО И ВОССТАНОВЛЕНО: Двойной перекрестный цикл для математического анализа спредов
		for ex_a_name, ob_a in orderbooks.items():
			for ex_b_name, ob_b in orderbooks.items():
				# Запрещаем сравнивать биржу саму с собой
				if ex_a_name == ex_b_name:
					continue
				
				# Передаем пары стаканов в математическое ядро для поиска чистой прибыли
				self.arbitrage_analyzer.calculate_spot_spread(
					symbol=symbol,
					exchange_a_name=ex_a_name,
					orderbook_a=ob_a,
					exchange_b_name=ex_b_name,
					orderbook_b=ob_b,
					transfer_fee=self.transfer_fee_usdt,
					base_volume=self.base_order_usdt,
					min_spread_pct=self.min_spread_pct,
					trade_fee_pct=self.estimated_trade_fee_pct
				)

	async def start(self):
		"""Запуск бесконечного асинхронного цикла межбиржевого сканирования."""
		self.is_running = True
		await self.init_all_exchanges()
		
		await self.network_client.get_session()
		print(f"\n⏱️ [АРБИТРАЖ] Сканер запущен (Базовый ордер: {self.base_order_usdt} USDT). Ожидание сигналов...\n", flush=True)
		
		while self.is_running:
			try:
				for symbol in self.monitored_symbols:
					if not self.is_running:
						break
					await self._scan_arbitrage_for_symbol(symbol)
				
				# Пауза между полными кругами опроса монет
				await asyncio.sleep(self.scan_delay_seconds)
			except asyncio.CancelledError:
				break
			except Exception as e:
				print(f"⚠️ [СКРИНЕР] Критическая ошибка в цикле: {e}")
				await asyncio.sleep(2)

	async def stop(self):
		"""Безопасная остановка менеджера с закрытием сессии соединений."""
		print("\n[MAIN] Завершение работы пользователем...")
		self.is_running = False
		await self.network_client.close()
		print("🚨 [АРБИТРАЖ] Все подключения к биржам закрыты.\n")
