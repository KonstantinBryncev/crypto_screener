import asyncio
import json
import os
from core.analyzer import ArbitrageAnalyzer
from network.client import AsyncHttpClient

class ArbitrageManager:
	def __init__(self):
		"""
		Менеджер межбиржевого арбитража криптовалют.
		Динамически подгружает абсолютно ВСЕ настройки из config_bot.json.
		"""
		self.arbitrage_analyzer = ArbitrageAnalyzer()
		self.network_client = AsyncHttpClient()
		self.is_running = False
		
		# Загружаем конфигурационный файл config_bot.json
		self.config = self._load_config()
		arb_settings = self.config.get("arbitrage", {})
		
		# Распределяем переменные из твоего файла настроек
		self.monitored_symbols = arb_settings.get("symbols", [
			"BTC/USDT", "ETH/USDT", "LTC/USDT", "XRP/USDT", 
			"SOL/USDT", "DOGE/USDT", "DOT/USDT", "LINK/USDT", 
			"AVAX/USDT", "TRX/USDT"
		])
		self.base_amount_usdt = float(arb_settings.get("base_order_usdt", 1000.0))
		self.transfer_fee = float(arb_settings.get("transfer_fee_usdt", 1.0))
		self.scan_delay = float(arb_settings.get("scan_delay_seconds", 3.0))
		self.min_spread_pct = float(arb_settings.get("min_spread_pct", -1.0))
		self.trade_fee_pct = float(arb_settings.get("estimated_trade_fee_pct", 0.002))
		
		# Динамически подгружаем анти-бан задержку из твоего JSON
		self.anti_ban_delay = float(arb_settings.get("anti_ban_delay_seconds", 0.5))

	def _load_config(self) -> dict:
		"""Вспомогательный метод для чтения config_bot.json из корня проекта"""
		current_dir = os.path.dirname(os.path.abspath(__file__))
		print(current_dir)
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
		print("==================================================")
		print("✅ [АРБИТРАЖ REST] Все прямые API-шлюзы успешно инициализированы.")

	async def _fetch_bybit(self, session, symbol: str) -> dict:
		pair = symbol.upper().replace('/', '')
		url = "https://api.bybit.com"
		params = {"category": "spot", "symbol": pair, "limit": 5}
		try:
			async with session.get(url, params=params, timeout=5) as resp:
				if resp.status == 200:
					data = await resp.json()
					res = data.get('result', {})
					if 'b' in res and 'a' in res:
						return {
							'bids': [[float(item[0]), float(item[1])] for item in res['b'] if item],
							'asks': [[float(item[0]), float(item[1])] for item in res['a'] if item]
						}
		except Exception:
			pass
		return None

	async def _fetch_bingx(self, session, symbol: str) -> dict:
		pair = symbol.upper().replace('/', '-')
		url = "https://api.bingx.com"
		params = {"symbol": pair, "limit": 5}
		try:
			async with session.get(url, params=params, timeout=5) as resp:
				if resp.status == 200:
					data = await resp.json()
					print(data)
					res = data.get('data', {})
					if 'bids' in res and 'asks' in res:
						return {
							'bids': [[float(item[0]), float(item[1])] for item in res['bids'] if item],
							'asks': [[float(item[0]), float(item[1])] for item in res['asks'] if item]
						}
		except Exception:
			pass
		return None

	async def _fetch_kucoin(self, session, symbol: str) -> dict:
		pair = symbol.upper().replace('/', '-')
		url = "https://api.kucoin.com"
		params = {"symbol": pair}
		try:
			async with session.get(url, params=params, timeout=5) as resp:
				if resp.status == 200:
					data = await resp.json()
					res = data.get('data', {})
					if 'bids' in res and 'asks' in res:
						return {
							'bids': [[float(item[0]), float(item[1])] for item in res['bids'] if item],
							'asks': [[float(item[0]), float(item[1])] for item in res['asks'] if item]
						}
		except Exception:
			pass
		return None

	async def _fetch_gate(self, session, symbol: str) -> dict:
		pair = symbol.upper().replace('/', '_')
		url = "https://api.gateio.ws"
		params = {"currency_pair": pair, "volatility_multiplier	mit": 5}
		try:
			async with session.get(url, params=params, timeout=5) as resp:
				if resp.status == 200:
					res = await resp.json()
					if 'bids' in res and 'asks' in res:
						return {
							'bids': [[float(item[0]), float(item[1])] for item in res['bids'] if item],
							'asks': [[float(item[0]), float(item[1])] for item in res['asks'] if item]
						}
		except Exception:
			pass
		return None

	async def _scan_arbitrage_for_symbol(self, session, symbol: str):
		# Чтобы не спамить биржи одновременно, запрашиваем их с микропаузами anti_ban
		ob_bybit = await self._fetch_bybit(session, symbol)
		await asyncio.sleep(self.anti_ban_delay)
		
		ob_bingx = await self._fetch_bingx(session, symbol)
		await asyncio.sleep(self.anti_ban_delay)
		
		ob_kucoin = await self._fetch_kucoin(session, symbol)
		await asyncio.sleep(self.anti_ban_delay)
		
		ob_gate = await self._fetch_gate(session, symbol)
		
		orderbooks = {}
		if ob_bybit: orderbooks['bybit'] = ob_bybit
		if ob_bingx: orderbooks['bingx'] = ob_bingx
		if ob_kucoin: orderbooks['kucoin'] = ob_kucoin
		if ob_gate: orderbooks['gate'] = ob_gate

		if len(orderbooks) < 2:
			return

		for ex_a_name, ob_a in orderbooks.items():
			for ex_b_name, ob_b in orderbooks.items():
				if ex_a_name == ex_b_name:
					continue
				
				try:
					self.arbitrage_analyzer.calculate_spot_spread(
						symbol=symbol,
						exchange_a_name=ex_a_name,
						orderbook_a=ob_a,
						exchange_b_name=ex_b_name,
						orderbook_b=ob_b,
						transfer_fee=self.transfer_fee,
						base_volume=self.base_amount_usdt,
						min_spread_pct=self.min_spread_pct,
						trade_fee_pct=self.trade_fee_pct
					)
				except Exception as analyzer_err:
					print(f"❌ Ошибка в ArbitrageAnalyzer для пары {symbol}: {analyzer_err}")

	async def start(self):
		self.is_running = True
		await self.init_all_exchanges()
		
		session = await self.network_client.get_session()
		print(f"\n⏱️ [АРБИТРАЖ] Сканер запущен (Базовый ордер: {self.base_amount_usdt} USDT). Ожидание сигналов...\n")
		
		while self.is_running:
			try:
				# Последовательно-параллельный обход с анти-бан задержками
				for symbol in self.monitored_symbols:
					if not self.is_running:
						break
					await self._scan_arbitrage_for_symbol(session, symbol)
				
				# Главная задержка круга сканирования из твоего файла конфигурации
				await asyncio.sleep(self.scan_delay)
			except asyncio.CancelledError:
				break
			except Exception as e:
				print(f"⚠️ [СКРИНЕР] Критическая ошибка в цикле: {e}")
				await asyncio.sleep(2)

	async def stop(self):
		print("\n[MAIN] Завершение работы пользователем...")
		self.is_running = False
		await self.network_client.close()
		print("🚨 [АРБИТРАЖ] Все подключения к биржам закрыты.\n")
