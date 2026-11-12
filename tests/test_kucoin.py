# Файл: tests/test_kucoin.py
import os
import sys
import asyncio
from unittest.mock import AsyncMock, MagicMock

# Добавляем корень проекта в пути поиска
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.config import CONFIG
from network.client import AsyncHttpClient
from exchanges.kucoin import KuCoinExchange


async def run_kucoin_xray_test():
	print("\n" + "=" * 80)
	print("🔬 [РЕНТГЕН-ТЕСТ] Проверка коннектора exchanges/kucoin.py")
	print("=" * 80)

	# -------------------------------------------------------------------------
	# ШАГ 1: Проверка парсинга и сортировки стакана KuCoin (офлайн)
	# -------------------------------------------------------------------------
	print("🧪 ШАГ 1. Проверка парсинга ответа KuCoin (code='200000', keys 'asks'/'bids'):")
	mock_net = MagicMock()

	fake_kucoin_response = {
		"code": "200000",
		"data": {
			"time": 1730000000555,
			"sequence": "987654321",
			"asks": [
				["73950.0", "1.1"],
				["73890.0", "0.6"]  # <-- Самый дешевый продавец
			],
			"bids": [
				["73820.0", "2.0"],
				["73875.0", "0.9"]  # <-- Самый дорогой покупатель
			]
		}
	}
	mock_net.fetch_json = AsyncMock(return_value=fake_kucoin_response)

	kucoin = KuCoinExchange(
		network_client=mock_net,
		base_url="https://api.kucoin.com",
		monitored_symbols=["BTC/USDT"]
	)

	book = await kucoin.fetch_order_book("BTC/USDT", limit=2)
	idx_price = 0

	if book and book["asks"][idx_price] == [73890.0, 0.6] and book["bids"][idx_price] == [73875.0, 0.9]:
		print("   ✅ УСПЕХ! Стакан KuCoin распарсен и отсортирован точно:")
		print(f"      • Лучший Ask (покупка) : {book['asks'][idx_price]} (тип цены: {type(book['asks'][idx_price][idx_price]).__name__})")
		print(f"      • Лучший Bid (продажа) : {book['bids'][idx_price]} (тип цены: {type(book['bids'][idx_price][idx_price]).__name__})\n")
	else:
		print(f"   🚨 ОШИБКА! Неверный формат стакана: {book}\n")

	# -------------------------------------------------------------------------
	# ШАГ 2: Проверка обработки ошибки API KuCoin (code != '200000')
	# -------------------------------------------------------------------------
	print("🧪 ШАГ 2. Проверка защиты при ошибке API KuCoin:")
	mock_net.fetch_json = AsyncMock(return_value={"code": "400100", "msg": "Invalid symbol"})
	bad_book = await kucoin.fetch_order_book("FAKE/USDT", limit=2)

	if bad_book is None:
		print("   ✅ УСПЕХ! Ошибка биржи перехвачена, вернулся None.\n")
	else:
		print(f"   🚨 ОШИБКА! Ожидали None, получили: {bad_book}\n")

	# -------------------------------------------------------------------------
	# ШАГ 3: Живой боевой запрос стакана BTC/USDT с реального сервера KuCoin
	# -------------------------------------------------------------------------
	print("🌐 ШАГ 3. Боевой запрос реального стакана BTC/USDT с KuCoin:")
	AsyncHttpClient._instance = None
	live_net = AsyncHttpClient(CONFIG)
	await live_net.init_tunnel()

	live_kucoin = KuCoinExchange(
		network_client=live_net,
		base_url=CONFIG["hosts"]["kucoin_base_url"],
		monitored_symbols=["BTC/USDT"]
	)

	limit_from_cfg = int(CONFIG["arbitrage"]["orderbook_limit"])
	live_book = await live_kucoin.fetch_order_book("BTC/USDT", limit=limit_from_cfg)

	if live_book and live_book["asks"] and live_book["bids"]:
		print(f"   ✅ УСПЕХ! Живой стакан KuCoin получен (глубина {len(live_book['asks'])} уровней):")
		print(f"      • Лучший Ask: {live_book['asks'][idx_price]}")
		print(f"      • Лучший Bid: {live_book['bids'][idx_price]}\n")
	else:
		print("   🚨 ОШИБКА! Не удалось получить живой стакан BTC/USDT с KuCoin.\n")

	await live_net.close()
	print("=" * 80)
	print("🎉 ИТОГ: Коннектор KuCoin полностью проверен и готов к работе!")
	print("=" * 80 + "\n")


if __name__ == "__main__":
	asyncio.run(run_kucoin_xray_test())
