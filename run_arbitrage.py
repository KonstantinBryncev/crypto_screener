import os
import sys
import time
import json
import asyncio
from datetime import datetime

# Подключаем твою единую сеть, базу данных и анализатор
from network.client import AsyncHttpClient
from database.storage import DBStorage
from core.analyzer import ArbitrageAnalyzer

def load_config():
	"""Загрузка конфигурационного файла из папки config"""
	base_dir = os.path.dirname(os.path.abspath(__file__))
	config_path = os.path.join(base_dir, "config", "config_bot.json")
	if os.path.exists(config_path):
		with open(config_path, "r", encoding="utf-8") as f:
			return json.load(f)
	return {}

class AsyncMarketScanner:
	def __init__(self, config):
		self.config = config
		
		# Инициализируем твой Singleton HTTP клиент (он сам поднимет xray.exe)
		self.network_client = AsyncHttpClient()
		
		# Забираем хосты строго из конфига, как ты просил
		hosts = config.get("hosts", {})
		try:
			self.hosts = {
				"bybit": hosts["bybit_base_url"],
				"kucoin": hosts["kucoin_base_url"],
				"okx": hosts["okx_base_url"],
				"gate.io": hosts["gate_base_url"],
				"bingx": hosts["bingx_base_url"]
			}
		except KeyError as e:
			print(f"🚨 [КРИТИЧЕСКАЯ ОШИБКА КОНФИГА]: В config_bot.json отсутствует хост: {e}")
			sys.exit(1)
		
		# Вытаскиваем все переменные арбитража ИСКЛЮЧИТЕЛЬНО из файла настроек
		arbitrage_settings = config.get("arbitrage", {})
		self.min_spread = arbitrage_settings.get("min_spread_percent", 0.5)
		self.max_spread = arbitrage_settings.get("max_spread_percent", 5.0)
		self.scan_delay = arbitrage_settings.get("scan_delay_seconds", 10.0)
		self.base_volume = arbitrage_settings.get("base_order_usdt", 500.0)
		
		# Переносим и комиссию в конфиг! Если её там нет, берем дефолт 0.1
		self.trade_fee = arbitrage_settings.get("trade_fee_percent", 0.1)
		
		self.analyzer = ArbitrageAnalyzer()
		self.pairs = []

	async def load_all_usdt_pairs(self):
		"""Загружает абсолютно все доступные спотовые пары к USDT со всех 5 бирж через защищенный клиент"""
		print("🔄 Собираем список доступных монет к USDT через защищенные туннели...")
		
		exchanges_endpoints = {
			"bybit": "/v5/market/instruments-info?category=spot",
			"okx": "/api/v5/public/instruments?instType=SPOT",
			"bingx": "/openApi/spot/v1/common/symbols",
			"gate.io": "/spot/currency_pairs",
			"kucoin": "/api/v1/symbols"
		}
		
		all_sets = []
		
		for exchange, endpoint in exchanges_endpoints.items():
			try:
				base_url = self.hosts[exchange].rstrip("/")
				if exchange == "gate.io":
					url = f"{base_url}/api/v4{endpoint}"
				else:
					url = f"{base_url}{endpoint}"
					
				# Тянем JSON через центральный клиент с Reality маскировкой
				data = await self.network_client.fetch_json(url, method="GET")
				if not data:
					print(f"⚠️ Биржа {exchange.upper()} вернула пустой ответ. Проверь туннель.")
					continue
				
				ex_pairs = set()
				
				if exchange == "bybit":
					for item in data.get("result", {}).get("list", []):
						if item.get("quoteCoin") == "USDT":
							base = item.get("baseCoin")
							ex_pairs.add(f"{base}/USDT")
							
				elif exchange == "okx":
					for item in data.get("data", []):
						if item.get("ctValCcy") == "USDT" or item.get("instId", "").endswith("-USDT"):
							base = item.get("baseCcy")
							ex_pairs.add(f"{base}/USDT")
							
				elif exchange == "bingx":
					for item in data.get("data", {}).get("symbols", []):
						if item.get("quoteAsset") == "USDT":
							base = item.get("baseAsset")
							ex_pairs.add(f"{base}/USDT")
							
				elif exchange == "gate.io":
					if isinstance(data, list):
						for item in data:
							if item.get("quote") == "USDT" and item.get("trade_status") == "tradable":
								base = item.get("base")
								ex_pairs.add(f"{base}/USDT")
							
				elif exchange == "kucoin":
					for item in data.get("data", []):
						if item.get("quoteCurrency") == "USDT" and item.get("enableTrading"):
							base = item.get("baseCurrency")
							ex_pairs.add(f"{base}/USDT")
				
				if ex_pairs:
					all_sets.append(ex_pairs)
					print(f"🔹 {exchange.upper()}: Пробита защита! Успешно найдено {len(ex_pairs)} пар к USDT")
					
			except Exception as e:
				print(f"⚠️ Не удалось загрузить пары с {exchange}: {e}")

		if all_sets:
			all_discovered = set.union(*all_sets)
			valid_pairs = []
			for pair in all_discovered:
				count = sum(1 for s in all_sets if pair in s)
				if count >= 2:
					valid_pairs.append(pair)
					
			self.pairs = sorted(valid_pairs)
			print(f"✅ Итог: К мониторингу готово {len(self.pairs)} общих торговых пар!")
		else:
			print("🚨 Критическая ошибка сети: откат к базовым BTC и ETH.")
			self.pairs = ["BTC/USDT", "ETH/USDT"]

	def _format_symbol(self, symbol: str, exchange: str) -> str:
		base, quote = symbol.split("/")
		if exchange in ["bybit", "okx"]:
			return f"{base}{quote}".upper()
		elif exchange == "gate.io":
			return f"{base}_I{quote}".replace("_IUSDT", "_USDT").upper()  # Корректируем под синтаксис Gate V4
		elif exchange in ["kucoin", "bingx"]:
			return f"{base}-{quote}".upper()
		return symbol

	async def fetch_orderbook(self, exchange: str, symbol: str) -> dict:
		"""Получение стакана напрямую через единый маскированный HTTP-клиент бота"""
		formatted_symbol = self._format_symbol(symbol, exchange)
		base_url = self.hosts[exchange].rstrip("/")
		
		url = ""
		params = {}
		if exchange == "bybit":
			url = f"{base_url}/v5/market/orderbook"
			params = {"category": "spot", "symbol": formatted_symbol, "limit": "5"}
		elif exchange == "okx":
			url = f"{base_url}/api/v5/market/books"
			params = {"instId": formatted_symbol, "sz": "5"}
		elif exchange == "bingx":
			url = f"{base_url}/openApi/spot/v1/market/depth"
			params = {"symbol": formatted_symbol, "limit": "5"}
		elif exchange == "gate.io":
			url = f"{base_url}/api/v4/spot/order_book"
			params = {"currency_pair": formatted_symbol, "limit": "5"}
		elif exchange == "kucoin":
			url = f"{base_url}/api/v1/market/orderbook/level2_depth20"
			params = {"symbol": formatted_symbol}

		try:
			data = await self.network_client.fetch_json(url, method="GET", params=params)
			if not data:
				return {}
				
			asks, bids = [], []

			if exchange == "bybit":
				result = data.get("result", {})
				asks = [[float(x[0]), float(x[1])] for x in result.get("a", [])]
				bids = [[float(x[0]), float(x[1])] for x in result.get("b", [])]
				
			elif exchange == "okx":
				result = data.get("data", [{}])[0]
				asks = [[float(x[0]), float(x[1])] for x in result.get("asks", [])]
				bids = [[float(x[0]), float(x[1])] for x in result.get("bids", [])]
				
			elif exchange == "bingx":
				result = data.get("data", {})
				asks = [[float(x[0]), float(x[1])] for x in result.get("asks", [])]
				bids = [[float(x[0]), float(x[1])] for x in result.get("bids", [])]
				
			elif exchange == "gate.io":
				asks = [[float(x[0]), float(x[1])] for x in data.get("asks", [])]
				bids = [[float(x[0]), float(x[1])] for x in data.get("bids", [])]
				
			elif exchange == "kucoin":
				result = data.get("data", {})
				asks = [[float(x[0]), float(x[1])] for x in result.get("asks", [])][:5]
				bids = [[float(x[0]), float(x[1])] for x in result.get("bids", [])][:5]

			return {"asks": asks, "bids": bids}
		except Exception:
			return {}

	async def scan_pair(self, symbol: str):
		"""Параллельный сбор стаканов по одной паре со всех бирж и вычисление спреда"""
		exchanges = ["bybit", "okx", "bingx", "gate.io", "kucoin"]
		tasks = [self.fetch_orderbook(ex, symbol) for ex in exchanges]
		results = await asyncio.gather(*tasks)
		
		orderbooks = {exchanges[i]: results[i] for i in range(len(exchanges)) if results[i] and (results[i].get("asks") or results[i].get("bids"))}

		for ex_a, ob_a in orderbooks.items():
			for ex_b, ob_b in orderbooks.items():
				if ex_a == ex_b:
					continue
				
				self.analyzer.calculate_spot_spread(
					symbol=symbol,
					exchange_a_name=ex_a,
					orderbook_a=ob_a,
					exchange_b_name=ex_b,
					orderbook_b=ob_b,
					base_volume=self.base_volume,
					min_spread_pct=self.min_spread,
					max_spread_pct=self.max_spread,
					trade_fee_pct=self.trade_fee
				)

	async def start_loop(self):
		await self.load_all_usdt_pairs()
		
		print("\n📊 Асинхронный радар-скринер запущен в БОЕВОМ туннельном режиме.")
		print(f"⚙️ Порог спреда: от {self.min_spread}% до {self.max_spread}%")
		print(f"💰 Рабочий объем ордера: {self.base_volume} USDT\n")

		while True:
			try:
				t_start = time.time()
				
				batch_size = 35
				for i in range(0, len(self.pairs), batch_size):
					batch = self.pairs[i:i+batch_size]
					scan_tasks = [self.scan_pair(pair) for pair in batch]
					await asyncio.gather(*scan_tasks)
					await asyncio.sleep(0.1)
				
				elapsed = time.time() - t_start
				sleep_time = max(0.1, self.scan_delay - elapsed)
				await asyncio.sleep(sleep_time)
				
			except KeyboardInterrupt:
				print("\n🛑 Скринер остановлен.")
				break
			except Exception as e:
				print(f"🚨 [ОШИБКА ЦИКЛА]: {e}")
				await asyncio.sleep(5)


def main():
	config = load_config()
	if not config:
		print("🚨 [ОШИБКА] config_bot.json не найден!")
		sys.exit(1)
		
	scanner = AsyncMarketScanner(config)
	try:
		asyncio.run(scanner.start_loop())
	finally:
		# Перед выходом гасим сессии и встроенный xray.exe из ОЗУ сервера
		asyncio.run(scanner.network_client.close())

if __name__ == "__main__":
	main()
