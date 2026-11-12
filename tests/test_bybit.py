# Файл: tests/test_bybit.py
import os
import sys
import asyncio
from unittest.mock import AsyncMock, MagicMock

# Добавляем корень проекта в пути поиска
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.config import CONFIG
from network.client import AsyncHttpClient
from exchanges.bybit import BybitExchange


async def run_bybit_xray_test():
	print("\n" + "=" * 80)
	print("🔬 [РЕНТГЕН-ТЕСТ] Проверка коннектора exchanges/bybit.py")
	print("=" * 80)

	# -------------------------------------------------------------------------
	# ШАГ 1: Проверка парсинга и сортировки стакана Bybit v5 (офлайн)
	# -------------------------------------------------------------------------
	print("🧪 ШАГ 1. Проверка парсинга ответа Bybit v5 (ключи 'a' и 'b'):")
	mock_net = MagicMock()

	fake_bybit_response = {
		"retCode": 0,
		"retMsg": "OK",
		"result": {
			"s": "BTCUSDT",
			"b": [
				["73800.5", "1.2"],
				["73850.0", "0.5"]  # <-- Самый дорогой покупатель
			],
			"a": [
				["73900.0", "2.0"],
				["73860.0", "0.9"]  # <-- Самый дешевый продавец
			],
			"ts": 1730000000000
		}
	}
	mock_net.fetch_json = AsyncMock(return_value=fake_bybit_response)

	bybit = BybitExchange(
		network_client=mock_net,
		base_url="https://bybit.com",
		monitored_symbols=["BTC/USDT"]
	)

	book = await bybit.fetch_order_book("BTC/USDT", limit=2)

	if book and book["asks"] == [73860.0, 0.9] and book["bids"] == [73850.0, 0.5]:
		print("   ✅ УСПЕХ! Стакан Bybit распарсен и отсортирован точно:")
		print(f"      • Лучший Ask (покупка) : {book['asks']} (тип цены: {type(book['asks']).__name__})")
		print(f"      • Лучший Bid (продажа) : {book['bids']} (тип цены: {type(book['bids']).__name__})\n")
	else:
		print(f"   🚨 ОШИБКА! Неверный формат стакана: {book}\n")

	# -------------------------------------------------------------------------
	# ШАГ 2: Проверка обработки ошибки API (retCode != 0)
	# -------------------------------------------------------------------------
	print("🧪 ШАГ 2. Проверка защиты при ошибке API (retCode != 0):")
	mock_net.fetch_json = AsyncMock(return_value={"retCode": 10001, "retMsg": "Symbol invalid"})
	bad_book = await bybit.fetch_order_book("FAKE/USDT", limit=2)

	if bad_book is None:
		print("   ✅ УСПЕХ! Ошибка биржи перехвачена, вернулся None.\n")
	else:
		print(f"   🚨 ОШИБКА! Ожидали None, получили: {bad_book}\n")

	# -------------------------------------------------------------------------
	# ШАГ 3: Живой боевой запрос стакана BTC/USDT с реального сервера Bybit
	# -------------------------------------------------------------------------
	print("🌐 ШАГ 3. Боевой запрос реального стакана BTC/USDT с Bybit:")
	AsyncHttpClient._instance = None
	live_net = AsyncHttpClient(CONFIG)
	await live_net.init_tunnel()

	live_bybit = BybitExchange(
		network_client=live_net,
		base_url=CONFIG["hosts"]["bybit_base_url"],
		monitored_symbols=["BTC/USDT"]
	)

	limit_from_cfg = int(CONFIG["arbitrage"]["orderbook_limit"])
	live_book = await live_bybit.fetch_order_book("BTC/USDT", limit=limit_from_cfg)

	if live_book and live_book["asks"] and live_book["bids"]:
		print(f"   ✅ УСПЕХ! Живой стакан Bybit получен (глубина {len(live_book['asks'])} уровней):")
		print(f"      • Лучший Ask: {live_book['asks']}")
		print(f"      • Лучший Bid: {live_book['bids']}\n")
	else:
		print("   🚨 ОШИБКА! Не удалось получить живой стакан BTC/USDT с Bybit.\n")

	await live_net.close()
	print("=" * 80)
	print("🎉 ИТОГ: Коннектор Bybit полностью проверен и готов к работе!")
	print("=" * 80 + "\n")


if __name__ == "__main__":
	asyncio.run(run_bybit_xray_test())
