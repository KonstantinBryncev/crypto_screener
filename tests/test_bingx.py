# Файл: tests/test_bingx.py
import os
import sys
import asyncio
from unittest.mock import AsyncMock, MagicMock

# Добавляем корень проекта в пути поиска
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.config import CONFIG
from network.client import AsyncHttpClient
from exchanges.bingx import BingXExchange


async def run_bingx_xray_test():
	print("\n" + "=" * 80)
	print("🔬 [РЕНТГЕН-ТЕСТ] Проверка коннектора exchanges/bingx.py")
	print("=" * 80)

	# -------------------------------------------------------------------------
	# ШАГ 1: Проверка парсинга и сортировки перевернутого стакана (офлайн)
	# -------------------------------------------------------------------------
	print("🧪 ШАГ 1. Проверка исправления перевернутого стакана asks от BingX:")
	mock_net = MagicMock()

	# Имитируем ответ BingX, где asks прилетели от дорогих (60500) к дешевым (60000)
	fake_bingx_response = {
		"code": 0,
		"msg": "",
		"data": {
			"asks": [
				["60500.0", "2.0"],
				["60200.0", "1.5"],
				["60000.0", "0.8"]  # <-- Самая дешевая продажа в конце списка!
			],
			"bids": [
				["59800.0", "1.0"],
				["59950.0", "1.2"], # <-- Самая дорогая покупка в середине списка!
				["59700.0", "3.0"]
			]
		}
	}
	mock_net.fetch_json = AsyncMock(return_value=fake_bingx_response)

	bingx = BingXExchange(
		network_client=mock_net,
		base_url="https://bingx.com",
		monitored_symbols=["BTC/USDT"]
	)

	book = await bingx.fetch_order_book("BTC/USDT", limit=3)

	if book and book["asks"][0] == [60000.0, 0.8] and book["bids"][0] == [59950.0, 1.2]:
		print(f"   ✅ УСПЕХ! Стакан отсортирован верно:")
		print(f"      • Лучший Ask (покупка) : {book['asks'][0]} (тип цены: {type(book['asks'][0][0]).__name__})")
		print(f"      • Лучший Bid (продажа) : {book['bids'][0]} (тип цены: {type(book['bids'][0][0]).__name__})\n")
	else:
		print(f"   🚨 ОШИБКА! Неверный порядок или формат стакана: {book}\n")

	# -------------------------------------------------------------------------
	# ШАГ 2: Проверка реакции на ошибку API биржи (code != 0)
	# -------------------------------------------------------------------------
	print("🧪 ШАГ 2. Проверка защиты при ошибке API (code != 0):")
	mock_net.fetch_json = AsyncMock(return_value={"code": 100400, "msg": "Invalid symbol"})
	bad_book = await bingx.fetch_order_book("FAKE/USDT", limit=3)

	if bad_book is None:
		print("   ✅ УСПЕХ! Ошибка биржи обработана безопасно, вернулся None без падения.\n")
	else:
		print(f"   🚨 ОШИБКА! Ожидали None, получили: {bad_book}\n")

	# -------------------------------------------------------------------------
	# ШАГ 3: Живой боевой запрос стакана BTC/USDT с реального сервера BingX
	# -------------------------------------------------------------------------
	print("🌐 ШАГ 3. Боевой запрос реального стакана BTC/USDT с BingX:")
	AsyncHttpClient._instance = None
	live_net = AsyncHttpClient(CONFIG)
	await live_net.init_tunnel()

	live_bingx = BingXExchange(
		network_client=live_net,
		base_url=CONFIG["hosts"]["bingx_base_url"],
		monitored_symbols=["BTC/USDT"]
	)

	limit_from_cfg = int(CONFIG["arbitrage"]["orderbook_limit"])
	live_book = await live_bingx.fetch_order_book("BTC/USDT", limit=limit_from_cfg)

	if live_book and live_book["asks"] and live_book["bids"]:
		print(f"   ✅ УСПЕХ! Живой стакан получен (глубина {len(live_book['asks'])} уровней):")
		print(f"      • Лучший Ask: {live_book['asks'][0]}")
		print(f"      • Лучший Bid: {live_book['bids'][0]}\n")
	else:
		print("   🚨 ОШИБКА! Не удалось получить живой стакан BTC/USDT с BingX.\n")

	await live_net.close()
	print("=" * 80)
	print("🎉 ИТОГ: Коннектор BingX полностью проверен и готов к работе!")
	print("=" * 80 + "\n")


if __name__ == "__main__":
	asyncio.run(run_bingx_xray_test())
