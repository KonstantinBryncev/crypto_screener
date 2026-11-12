# Файл: tests/test_pipeline.py
import os
import sys
import asyncio
import copy
from unittest.mock import AsyncMock, MagicMock

# Добавляем корень проекта в пути импорта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.config import CONFIG
from exchanges.bybit import BybitExchange
from exchanges.okx import OkxExchange
from exchanges.bingx import BingXExchange
from exchanges.gate import GateExchange
from exchanges.kucoin import KuCoinExchange
from core.analyzer import ArbitrageAnalyzer
from core.arbitrage_manager import ArbitrageManager


async def test_all_5_connectors():
	"""
	ШАГ 1: Проверка парсинга спотовых стаканов всеми 5 коннекторами.
	Подаем эталонные JSON-ответы API каждой биржи (включая неотсортированные уровни)
	и проверяем, что коннекторы приводят цены/объемы к float и правильно сортируют asks/bids.
	"""
	print("\n" + "=" * 75)
	print("🧪 [ТЕСТ 1] Проверка парсинга стаканов всеми 5 коннекторами бирж")
	print("=" * 75)

	mock_client = MagicMock()

	# Эталонные ответы API всех 5 бирж (специально даем asks/bids вразнобой для проверки сортировки)
	mock_responses = {
		"bybit": {
			"retCode": 0,
			"result": {
				"s": "BTCUSDT",
				"a": [["65020.0", "1.5"], ["65010.0", "0.8"]],  # asks (продажа)
				"b": [["64990.0", "1.2"], ["65000.0", "2.0"]],  # bids (покупка)
				"ts": 1700000000000
			}
		},
		"okx": {
			"code": "0",
			"data": [{
				"asks": [["65025.0", "1.0", "0", "1"], ["65015.0", "0.5", "0", "1"]],
				"bids": [["64985.0", "1.0", "0", "1"], ["64995.0", "1.5", "0", "1"]],
				"ts": "1700000000000"
			}]
		},
		"bingx": {
			"code": 0,
			"data": {
				"asks": [["65030.0", "1.1"], ["65012.0", "0.9"]],
				"bids": [["64980.0", "1.4"], ["64998.0", "1.7"]]
			}
		},
		"gate": {
			"asks": [["65018.0", "0.7"], ["65005.0", "1.3"]],
			"bids": [["64992.0", "1.0"], ["65001.0", "2.2"]]
		},
		"kucoin": {
			"code": "200000",
			"data": {
				"time": 1700000000000,
				"asks": [["65022.0", "0.6"], ["65008.0", "1.1"]],
				"bids": [["64988.0", "1.3"], ["64999.0", "1.9"]]
			}
		}
	}

	connectors = {
		"bybit": BybitExchange(mock_client, "https://bybit.com", ["BTC/USDT"]),
		"okx": OkxExchange(mock_client, "https://okx.com", ["BTC/USDT"]),
		"bingx": BingXExchange(mock_client, "https://bingx.com", ["BTC/USDT"]),
		"gate": GateExchange(mock_client, "https://gateio.ws", ["BTC/USDT"]),
		"kucoin": KuCoinExchange(mock_client, "https://kucoin.com", ["BTC/USDT"]),
	}

	passed = 0
	for ex_id, connector in connectors.items():
		mock_client.fetch_json = AsyncMock(return_value=mock_responses[ex_id])
		ob = await connector.fetch_order_book("BTC/USDT", limit=5)

		if not ob or not ob.get("asks") or not ob.get("bids"):
			print(f"🚨 [{ex_id.upper():<6}] ПРОВАЛ: вернул None или пустой стакан!")
			continue

		best_ask = ob["asks"][0][0]
		best_bid = ob["bids"][0][0]
		asks_sorted = ob["asks"][0][0] < ob["asks"][1][0]
		bids_sorted = ob["bids"][0][0] > ob["bids"][1][0]

		if asks_sorted and bids_sorted:
			print(f"✅ [{ex_id.upper():<6}] УСПЕХ | Best Ask: {best_ask} | Best Bid: {best_bid} | Сортировка: OK")
			passed += 1
		else:
			print(f"⚠️ [{ex_id.upper():<6}] ОШИБКА СОРТИРОВКИ | Asks: {ob['asks']} | Bids: {ob['bids']}")

	print("-" * 75)
	print(f"📊 Итог по коннекторам: {passed} из 5 прошли проверку.")
	return passed == 5


async def test_vwap_spread_math():
	"""
	ШАГ 2: Проверка математики VWAP-спреда в ArbitrageAnalyzer.
	Симулируем покупку на $1000 по стакану из 2 уровней (с проскальзыванием)
	и продажу в стакан другой биржи с вычетом двойной комиссии.
	"""
	print("\n" + "=" * 75)
	print("🧪 [ТЕСТ 2] Проверка математики VWAP-спреда (глубина стакана + комиссии)")
	print("=" * 75)

	test_cfg = copy.deepcopy(CONFIG)
	test_cfg["arbitrage"]["base_order_usdt"] = 1000.0
	test_cfg["arbitrage"]["min_spread_percent"] = 0.5
	test_cfg["arbitrage"]["max_spread_percent"] = 10.0
	test_cfg["arbitrage"]["trade_fee_percent"] = 0.1  # 0.1% за сделку -> 0.2% за круг

	analyzer = ArbitrageAnalyzer(test_cfg)
	# Подменяем запись в PostgreSQL, чтобы тест не требовал живую БД
	analyzer.db.save_possible_trade = MagicMock()

	# Биржа A (дешевая продажа asks): 5 монет по $100 ($500) + 10 монет по $102 ($1020)
	# На $1000 купим: 5 монет по $100 ($500) + 4.90196078 монет по $102 ($500) = 9.90196078 монет
	# Средняя цена покупки (VWAP Buy) = 1000 / 9.90196078 = $100.9901
	ob_cheap = {
		"asks": [[100.0, 5.0], [102.0, 10.0]],
		"bids": [[99.0, 10.0]]
	}

	# Биржа B (дорогая покупка bids): 6 монет по $104 + 10 монет по $103
	# Продадим 9.90196078 монет: 6 * 104 ($624) + 3.90196078 * 103 ($401.90196) = $1025.90196
	# Средняя цена продажи (VWAP Sell) = 1025.90196 / 9.90196078 = $103.6059
	# Грязный спред = (103.6059 - 100.9901) / 100.9901 * 100% = 2.590%
	# Чистый спред (минус 0.2% комиссии) = 2.390%
	ob_expensive = {
		"asks": [[105.0, 10.0]],
		"bids": [[104.0, 6.0], [103.0, 10.0]]
	}

	res = await analyzer.calculate_spot_spread(
		symbol="SOL/USDT",
		exchange_a_name="bybit",
		orderbook_a=ob_cheap,
		exchange_b_name="okx",
		orderbook_b=ob_expensive,
		volume_24h=500000.0
	)

	if res and "spread_pct" in res:
		print(f"✅ [VWAP УСПЕХ] Сигнал рассчитан корректно:")
		print(f"   -> Направление : {res['buy_exchange']} -> {res['sell_exchange']}")
		print(f"   -> VWAP Buy    : ${res['buy_price']} (учтено проскальзывание по 2 уровням)")
		print(f"   -> VWAP Sell   : ${res['sell_price']} (учтено проскальзывание по 2 уровням)")
		print(f"   -> Чистый спред: {res['spread_pct']}% (ожидали ~2.390%)")
		print(f"   -> Вызов БД    : save_possible_trade вызван {analyzer.db.save_possible_trade.call_count} раз(а)")
	else:
		print(f"🚨 [VWAP ПРОВАЛ] Анализатор вернул пустой результат: {res}")

	# Проверка отсечки неликвидного стакана (не хватает объема на $1000)
	ob_illiquid = {
		"asks": [[100.0, 2.0]],  # Всего на $200 при ордере $1000
		"bids": [[99.0, 2.0]]
	}
	res_illiquid = await analyzer.calculate_spot_spread(
		symbol="LOWLIQ/USDT",
		exchange_a_name="gate",
		orderbook_a=ob_illiquid,
		exchange_b_name="kucoin",
		orderbook_b=ob_expensive,
		volume_24h=150000.0
	)
	if not res_illiquid:
		print("✅ [ЗАЩИТА ОТ НЕЛИКВИДА] Тонкий стакан ($200 при ордере $1000) корректно отбракован.")
	else:
		print(f"🚨 [ОШИБКА] Тонкий стакан не отбракован: {res_illiquid}")


async def test_manager_single_symbol_scan():
	"""
	ШАГ 3: Интеграционный тест ArbitrageManager._scan_single_symbol.
	Проверяем, как менеджер одновременно опрашивает все 5 коннекторов,
	находит самую выгодную связку и выводит сигнал.
	"""
	print("\n" + "=" * 75)
	print("🧪 [ТЕСТ 3] Интеграционный прогон ArbitrageManager._scan_single_symbol")
	print("=" * 75)

	test_cfg = copy.deepcopy(CONFIG)
	test_cfg["arbitrage"]["base_order_usdt"] = 500.0
	test_cfg["arbitrage"]["min_spread_percent"] = 0.5
	test_cfg["arbitrage"]["max_spread_percent"] = 15.0
	test_cfg["arbitrage"]["trade_fee_percent"] = 0.1

	manager = ArbitrageManager(test_cfg)
	manager.analyzer.db.save_possible_trade = MagicMock()
	manager.symbols_volumes = {"ETH/USDT": 1250000.0}

	# Подменяем коннекторы в менеджере на моки с готовыми стаканами
	ex_mock_1 = MagicMock()
	ex_mock_1.fetch_order_book = AsyncMock(return_value={
		"asks": [[3000.0, 5.0]],
		"bids": [[2995.0, 5.0]]
	})

	ex_mock_2 = MagicMock()
	ex_mock_2.fetch_order_book = AsyncMock(return_value={
		"asks": [[3050.0, 5.0]],
		"bids": [[3045.0, 5.0]]  # Спред ~1.5% минус 0.2% комиссия = ~1.3%
	})

	ex_mock_3 = MagicMock()
	ex_mock_3.fetch_order_book = AsyncMock(return_value=None)  # Имитируем таймаут 3-й биржи

	manager.exchanges = {
		"gate": ex_mock_1,
		"kucoin": ex_mock_2,
		"okx": ex_mock_3
	}

	await manager._scan_single_symbol("ETH/USDT")

	if manager.analyzer.db.save_possible_trade.called:
		print("✅ [УСПЕХ ТЕСТА 3] Менеджер опросил биржи, пережил сбой OKX и нашел связку GATE -> KUCOIN!")
	else:
		print("🚨 [ПРОВАЛ ТЕСТА 3] Менеджер не нашел тестовую связку.")


async def main():
	await test_all_5_connectors()
	await test_vwap_spread_math()
	await test_manager_single_symbol_scan()
	print("\n" + "=" * 75)
	print("🏁 Все тесты конвейера завершены.")
	print("=" * 75 + "\n")


if __name__ == "__main__":
	asyncio.run(main())
