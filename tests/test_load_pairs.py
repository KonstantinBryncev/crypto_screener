# Файл: tests/test_load_pairs.py
import os
import sys
import asyncio
import copy
from unittest.mock import AsyncMock

# Добавляем корень проекта в пути импорта, чтобы видеть config, core и network
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.config import CONFIG
from core.arbitrage_manager import ArbitrageManager


async def run_xray_diagnostic():
	print("\n" + "=" * 80)
	print("🔬 [РЕНТГЕН-ТЕСТ] Пошаговая диагностика метода load_all_usdt_pairs()")
	print("=" * 80)

	# 1. Готовим копию твоего боевого конфига для теста
	test_cfg = copy.deepcopy(CONFIG)
	test_cfg["network"]["tunnel_warmup_seconds"] = 0.01  # Чтобы не ждать 4 секунды в тесте
	
	# Ставим четкий порог фильтрации: $500,000 за 24 часа
	min_vol_threshold = 500_000.0
	test_cfg["arbitrage"]["min_volume_24h_usdt"] = min_vol_threshold

	# Убеждаемся, что все 5 хостов прописаны для теста
	test_cfg["hosts"] = {
		"bybit_base_url": "https://bybit.com",
		"okx_base_url": "https://okx.com",
		"bingx_base_url": "https://bingx.com",
		"gate_base_url": "https://gateio.ws",
		"kucoin_base_url": "https://kucoin.com",
	}

	manager = ArbitrageManager(test_cfg)

	# Подменяем запуск туннеля, чтобы тест шел мгновенно без поднятия Xray
	manager.network_client.init_tunnel = AsyncMock(return_value=True)

	# 2. Реалистичные сырые ответы всех 5 бирж (как они приходят в жизни)
	raw_exchange_payloads = {
		"bybit": {
			"result": {
				"list": [
					# BTC/USDT: 1500 BTC * $65,000 = $97,500,000 -> ПРОХОДИТ
					{"symbol": "BTCUSDT", "volume24h": "1500", "lastPrice": "65000"},
					# SOL/USDT: 10000 SOL * $150 = $1,500,000 -> ПРОХОДИТ
					{"symbol": "SOLUSDT", "volume24h": "10000", "lastPrice": "150"},
					# PEPE/USDT: объем $120,000 (< $500,000) -> ДОЛЖЕН ОТСЕЯТЬСЯ по объему
					{"symbol": "PEPEUSDT", "volume24h": "12000000000", "lastPrice": "0.00001"},
					# ETH/BTC: пара не к USDT -> ДОЛЖНА ИГНОРИРОВАТЬСЯ
					{"symbol": "ETHBTC", "volume24h": "500", "lastPrice": "0.05"},
				]
			}
		},
		"okx": {
			"data": [
				# BTC/USDT: volCcy24h сразу в USDT = $102,500,000 -> ПРОХОДИТ
				{"instId": "BTC-USDT", "volCcy24h": "102500000"},
				# ETH/USDT: $45,000,000 -> ПРОХОДИТ
				{"instId": "ETH-USDT", "volCcy24h": "45000000"},
				# TON/USDT: есть только на OKX ($2,000,000) -> ОТСЕЕТСЯ при пересечении (1 биржа)
				{"instId": "TON-USDT", "volCcy24h": "2000000"},
			]
		},
		"bingx": {
			"data": [
				# ETH/USDT: 15000 ETH * $3,000 = $45,000,000 -> ПРОХОДИТ
				{"symbol": "ETH-USDT", "volume": "15000", "lastPrice": "3000"},
				# XRP/USDT: 2000000 XRP * $0.60 = $1,200,000 -> ПРОХОДИТ
				{"symbol": "XRP-USDT", "volume": "2000000", "lastPrice": "0.60"},
			]
		},
		"gate": [
			# SOL/USDT: quote_volume = $1,700,000 (в нижнем регистре sol_usdt для проверки .upper()) -> ПРОХОДИТ
			{"currency_pair": "sol_USDT", "quote_volume": "1700000"},
			# XRP/USDT: quote_volume = $1,400,000 -> ПРОХОДИТ
			{"currency_pair": "XRP_USDT", "quote_volume": "1400000"},
			# DOGE/USDT: quote_volume = $300,000 (< $500,000) -> ОТСЕЕТСЯ по объему
			{"currency_pair": "DOGE_USDT", "quote_volume": "300000"},
		],
		"kucoin": {
			"data": {
				"ticker": [
					# BTC/USDT: volValue = $80,000,000 -> ПРОХОДИТ
					{"symbol": "BTC-USDT", "volValue": "80000000"},
					# XRP/USDT: volValue = $1,000,000 -> ПРОХОДИТ
					{"symbol": "XRP-USDT", "volValue": "1000000"},
				]
			}
		}
	}

	print(f"⚙️  Порог фильтрации объема: ${min_vol_threshold:,.0f} за 24ч\n")
	print("📥 ШАГ 1. Что отдаем на вход функции (сырые тикеры бирж):")
	print("   • BYBIT  : BTCUSDT ($97.5M), SOLUSDT ($1.5M), PEPEUSDT ($120k - мало), ETHBTC (не USDT)")
	print("   • OKX    : BTC-USDT ($102.5M), ETH-USDT ($45M), TON-USDT ($2M - только на 1 бирже)")
	print("   • BINGX  : ETH-USDT ($45M), XRP-USDT ($1.2M)")
	print("   • GATE   : sol_USDT ($1.7M), XRP_USDT ($1.4M), DOGE_USDT ($300k - мало)")
	print("   • KUCOIN : BTC-USDT ($80M), XRP-USDT ($1M)\n")

	# Перехватчик сетевых запросов с выводом каждого шага в консоль
	async def traced_fetch_json(url: str, method: str = "GET"):
		if "bybit.com" in url:
			print(f"🌐 [HTTP GET] {url} -> Отдаем JSON Bybit...")
			return raw_exchange_payloads["bybit"]
		elif "okx.com" in url:
			print(f"🌐 [HTTP GET] {url} -> Отдаем JSON OKX...")
			return raw_exchange_payloads["okx"]
		elif "bingx.com" in url:
			print(f"🌐 [HTTP GET] {url} -> Отдаем JSON BingX...")
			return raw_exchange_payloads["bingx"]
		elif "gateio.ws" in url:
			print(f"🌐 [HTTP GET] {url} -> Отдаем JSON Gate.io...")
			return raw_exchange_payloads["gate"]
		elif "kucoin.com" in url:
			print(f"🌐 [HTTP GET] {url} -> Отдаем JSON KuCoin...")
			return raw_exchange_payloads["kucoin"]
		print(f"⚠️ [HTTP GET] Неизвестный URL: {url}")
		return None

	manager.network_client.fetch_json = AsyncMock(side_effect=traced_fetch_json)

	print("🚀 ШАГ 2. Запускаем load_all_usdt_pairs():")
	print("-" * 80)
	await manager.load_all_usdt_pairs()
	print("-" * 80)

	# 3. Детальный разбор того, что получилось на выходе
	print("\n📊 ШАГ 3. Аудит итогового списка self.monitored_symbols и средних объемов:")
	
	expected_results = {
		"BTC/USDT": (97_500_000 + 102_500_000 + 80_000_000) / 3,  # Bybit + OKX + KuCoin
		"ETH/USDT": (45_000_000 + 45_000_000) / 2,                # OKX + BingX
		"SOL/USDT": (1_500_000 + 1_700_000) / 2,                  # Bybit + Gate
		"XRP/USDT": (1_200_000 + 1_400_000 + 1_000_000) / 3,      # BingX + Gate + KuCoin
	}

	all_passed = True

	for sym in manager.monitored_symbols:
		actual_vol = manager.symbols_volumes.get(sym, 0.0)
		exp_vol = expected_results.get(sym)
		
		if exp_vol is not None and abs(actual_vol - exp_vol) < 1.0:
			print(f"   ✅ {sym:<10} | ПРОШЛА | Средний объем: ${actual_vol:>14,.2f} (расчет точный)")
		else:
			print(f"   🚨 {sym:<10} | ОШИБКА | Получен объем ${actual_vol:,.2f}, ожидали {exp_vol}")
			all_passed = False

	# Проверяем, что мусорные и одиночные пары НЕ пролезли в финал
	forbidden_pairs = ["PEPE/USDT", "DOGE/USDT", "TON/USDT", "ETH/BTC"]
	print("\n🛡️  ШАГ 4. Проверка отсева неликвида и одиночных монет:")
	for bad_sym in forbidden_pairs:
		if bad_sym not in manager.monitored_symbols:
			print(f"   ✅ {bad_sym:<10} | Корректно отсеяна фильтром")
		else:
			print(f"   🚨 {bad_sym:<10} | ОШИБКА! Эта пара НЕ должна была попасть в финал!")
			all_passed = False

	# Итоговый вердикт
	print("\n" + "=" * 80)
	if all_passed and set(manager.monitored_symbols) == set(expected_results.keys()):
		print("🎉 ИТОГ: Функция load_all_usdt_pairs() работает ИДЕАЛЬНО! Все 5 бирж распарсились без потерь.")
	else:
		print(f"💥 ИТОГ: Обнаружено расхождение! Получили: {manager.monitored_symbols}, ожидали: {sorted(expected_results.keys())}")
	print("=" * 80 + "\n")


if __name__ == "__main__":
	asyncio.run(run_xray_diagnostic())
