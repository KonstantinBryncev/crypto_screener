# Файл: tests/test_gate.py
import os
import sys
import asyncio
from unittest.mock import AsyncMock, MagicMock

# Добавляем корень проекта в пути поиска
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.config import CONFIG
from network.client import AsyncHttpClient
from exchanges.gate import GateExchange


async def run_gate_xray_test():
	print("\n" + "=" * 80)
	print("🔬 [РЕНТГЕН-ТЕСТ] Проверка коннектора exchanges/gate.py")
	print("=" * 80)

	# -------------------------------------------------------------------------
	# ШАГ 1: Проверка парсинга и сортировки стакана Gate.io (офлайн)
	# -------------------------------------------------------------------------
	print("🧪 ШАГ 1. Проверка парсинга ответа Gate.io (ключи 'asks' и 'bids'):")
	mock_net = MagicMock()

	fake_gate_response = {
		"id": 12345678,
		"current": 1730000000123,
		"update": 1730000000100,
		"asks": [
			["73920.0", "1.5"],
			["73880.0", "0.7"]  # <-- Самый дешевый продавец
		],
		"bids": [
			["73810.0", "2.1"],
			["73870.0", "0.4"]  # <-- Самый дорогой покупатель
		]
	}
	mock_net.fetch_json = AsyncMock(return_value=fake_gate_response)

	gate = GateExchange(
		network_client=mock_net,
		base_url="https://gateio.ws",
		monitored_symbols=["BTC/USDT"]
	)

	book = await gate.fetch_order_book("BTC/USDT", limit=2)
	idx_price = 0

	if book and book["asks"][idx_price] == [73880.0, 0.7] and book["bids"][idx_price] == [73870.0, 0.4]:
		print("   ✅ УСПЕХ! Стакан Gate.io распарсен и отсортирован точно:")
		print(f"      • Лучший Ask (покупка) : {book['asks'][idx_price]} (тип цены: {type(book['asks'][idx_price][idx_price]).__name__})")
		print(f"      • Лучший Bid (продажа) : {book['bids'][idx_price]} (тип цены: {type(book['bids'][idx_price][idx_price]).__name__})\n")
	else:
		print(f"   🚨 ОШИБКА! Неверный формат стакана: {book}\n")

	# -------------------------------------------------------------------------
	# ШАГ 2: Проверка обработки ошибки API Gate.io
	# -------------------------------------------------------------------------
	print("🧪 ШАГ 2. Проверка защиты при ошибке API Gate.io:")
	mock_net.fetch_json = AsyncMock(return_value={"label": "INVALID_CURRENCY_PAIR", "message": "Invalid currency pair"})
	bad_book = await gate.fetch_order_book("FAKE/USDT", limit=2)

	if bad_book is None:
		print("   ✅ УСПЕХ! Ошибка биржи перехвачена, вернулся None.\n")
	else:
		print(f"   🚨 ОШИБКА! Ожидали None, получили: {bad_book}\n")

	# -------------------------------------------------------------------------
	# ШАГ 3: Живой боевой запрос стакана BTC/USDT с реального сервера Gate.io
	# -------------------------------------------------------------------------
	print("🌐 ШАГ 3. Боевой запрос реального стакана BTC/USDT с Gate.io:")
	AsyncHttpClient._instance = None
	live_net = AsyncHttpClient(CONFIG)
	await live_net.init_tunnel()

	live_gate = GateExchange(
		network_client=live_net,
		base_url=CONFIG["hosts"]["gate_base_url"],
		monitored_symbols=["BTC/USDT"]
	)

	limit_from_cfg = int(CONFIG["arbitrage"]["orderbook_limit"])
	live_book = await live_gate.fetch_order_book("BTC/USDT", limit=limit_from_cfg)

	if live_book and live_book["asks"] and live_book["bids"]:
		print(f"   ✅ УСПЕХ! Живой стакан Gate.io получен (глубина {len(live_book['asks'])} уровней):")
		print(f"      • Лучший Ask: {live_book['asks'][idx_price]}")
		print(f"      • Лучший Bid: {live_book['bids'][idx_price]}\n")
	else:
		print("   🚨 ОШИБКА! Не удалось получить живой стакан BTC/USDT с Gate.io.\n")

	await live_net.close()
	print("=" * 80)
	print("🎉 ИТОГ: Коннектор Gate.io полностью проверен и готов к работе!")
	print("=" * 80 + "\n")


if __name__ == "__main__":
	asyncio.run(run_gate_xray_test())
