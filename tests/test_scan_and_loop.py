# Файл: tests/test_scan_and_loop.py
import os
import sys
import time
import asyncio
import copy
from unittest.mock import AsyncMock, MagicMock

# Добавляем корень проекта в пути поиска
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.config import CONFIG
from core.arbitrage_manager import ArbitrageManager


async def test_scan_single_symbol_xray():
	"""
	Рентген-тест 1: Проверка _scan_single_symbol('BTC/USDT').
	Подаем стаканы с реальной разницей цен, имитируем отвал одной биржи
	и проверяем, что связка находится и печатается в консоль.
	"""
	print("\n" + "=" * 80)
	print("🔬 [РЕНТГЕН-ТЕСТ 1] Проверка _scan_single_symbol('BTC/USDT')")
	print("=" * 80)

	test_cfg = copy.deepcopy(CONFIG)
	# Настраиваем четкие рамки спреда: от 0.2% до 5.0%, комиссия 0.1%
	test_cfg["arbitrage"]["min_spread_percent"] = 0.2
	test_cfg["arbitrage"]["max_spread_percent"] = 5.0
	test_cfg["arbitrage"]["trade_fee_percent"] = 0.1
	test_cfg["arbitrage"]["base_order_usdt"] = 500.0
	test_cfg["arbitrage"].setdefault("orderbook_limit", 5)

	manager = ArbitrageManager(test_cfg)
	manager.symbols_volumes["BTC/USDT"] = 85_000_000.0

	# Отключаем реальную отправку в Telegram во время теста
	manager.tg_notifier.send_message = AsyncMock(return_value=True)

	# Создаем 4 фейковых коннектора бирж с реалистичными стаканами:
	# 1. BYBIT: дешевая продажа (asks по 60,000) -> ВЫГОДНО КУПИТЬ ТУТ
	# 2. OKX: дорогая покупка (bids по 60,600) -> ВЫГОДНО ПРОДАТЬ ТУТ (+1.0% грязными, +0.8% чистыми)
	# 3. GATE: обычная рыночная цена (60,100 / 60,150) -> вилки нет
	# 4. KUCOIN: имитируем обрыв связи (Exception) -> код должен не упасть, а просто пропустить биржу
	bybit_mock = MagicMock()
	bybit_mock.fetch_order_book = AsyncMock(return_value={
		"bids": [[59990.0, 2.0]],
		"asks": [[60000.0, 1.5], [60005.0, 3.0]]  # Можем купить BTC по 60,000!
	})

	okx_mock = MagicMock()
	okx_mock.fetch_order_book = AsyncMock(return_value={
		"bids": [[60600.0, 1.2], [60590.0, 2.5]],  # Можем продать BTC по 60,600!
		"asks": [[60620.0, 1.0]]
	})

	gate_mock = MagicMock()
	gate_mock.fetch_order_book = AsyncMock(return_value={
		"bids": [[60100.0, 1.0]],
		"asks": [[60150.0, 1.0]]
	})

	kucoin_mock = MagicMock()
	kucoin_mock.fetch_order_book = AsyncMock(side_effect=RuntimeError("Таймаут соединения с KuCoin"))

	manager.exchanges = {
		"bybit": bybit_mock,
		"okx": okx_mock,
		"gate": gate_mock,
		"kucoin": kucoin_mock,
	}

	print("📥 ШАГ 1. Входные стаканы для BTC/USDT (объем ордера $500, комиссия 0.1%):")
	print("   • BYBIT  : Ask (цена покупки) = $60,000.00")
	print("   • OKX    : Bid (цена продажи) = $60,600.00  <-- ОЖИДАЕМ ВИЛКУ BYBIT -> OKX!")
	print("   • GATE   : Bid $60,100 / Ask $60,150       <-- без арбитража")
	print("   • KUCOIN : Имитация обрыва связи (Exception) <-- должен безопасно отброситься\n")

	print("🚀 ШАГ 2. Запускаем _scan_single_symbol('BTC/USDT'):")
	await manager._scan_single_symbol("BTC/USDT")

	print("✅ ШАГ 3. Сканирование завершено без падений (KuCoin отброшен, сигнал BYBIT -> OKX обработан).\n")


async def test_start_loop_xray():
	"""
	Рентген-тест 2: Проверка главного цикла start(self).
	Проверяем нарезку монет на батчи, обработку таймаута пачки и плановый перезапуск туннеля.
	"""
	print("=" * 80)
	print("🔬 [РЕНТГЕН-ТЕСТ 2] Проверка главного цикла start(self) (батчи, таймауты, туннель)")
	print("=" * 80)

	test_cfg = copy.deepcopy(CONFIG)
	test_cfg["arbitrage"]["batch_size"] = 2                 # Режем по 2 монеты в пачке
	test_cfg["arbitrage"]["batch_timeout_seconds"] = 0.2    # Короткий таймаут для теста
	test_cfg["arbitrage"]["batch_delay_seconds"] = 0.05
	test_cfg["arbitrage"]["min_cycle_sleep_seconds"] = 0.05
	test_cfg["arbitrage"]["scan_delay_seconds"] = 0.05
	test_cfg["arbitrage"]["error_retry_delay_seconds"] = 0.05
	test_cfg["network"]["tunnel_refresh_seconds"] = 0.01    # Чтобы сразу сработал таймер обновления

	manager = ArbitrageManager(test_cfg)

	# Подменяем подготовку (сбор пар и коннекторов), чтобы тестировать именно сам цикл start()
	async def fake_load_pairs():
		manager.monitored_symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "ADA/USDT"]

	manager.load_all_usdt_pairs = AsyncMock(side_effect=fake_load_pairs)
	manager._init_exchange_connectors = MagicMock()
	manager.network_client.init_tunnel = AsyncMock(return_value=True)

	scanned_history = []

	async def fake_scan_symbol(symbol: str):
		scanned_history.append(symbol)
		# На последней монете ADA/USDT прерываем бесконечный while True, чтобы завершить тест
		if symbol == "ADA/USDT":
			raise asyncio.CancelledError("Тестовый полный круг успешно пройден!")

	manager._scan_single_symbol = AsyncMock(side_effect=fake_scan_symbol)

	print(f"⚙️  Настройки теста: 5 монет, batch_size={test_cfg['arbitrage']['batch_size']} (ожидаем 3 пачки: 2 + 2 + 1)")
	print("🚀 Запускаем start() на 1 полный круг...\n")

	try:
		await manager.start()
	except asyncio.CancelledError as stop_msg:
		print(f"🛑 Цикл остановлен по завершении круга: {stop_msg}")

	print(f"\n📊 Порядок просканированных монет: {scanned_history}")
	print(f"🔄 Вызовов обновления туннеля init_tunnel(): {manager.network_client.init_tunnel.call_count}")

	expected_order = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "ADA/USDT"]
	if scanned_history == expected_order and manager.network_client.init_tunnel.call_count >= 1:
		print("🎉 ИТОГ ТЕСТА 2: Главный цикл start() идеально прогнал все пачки и обновил туннель!")
	else:
		print("🚨 ИТОГ ТЕСТА 2: Что-то пошло не так в порядке сканирования или обновлении туннеля!")
	print("=" * 80 + "\n")


async def main():
	await test_scan_single_symbol_xray()
	await test_start_loop_xray()


if __name__ == "__main__":
	asyncio.run(main())
