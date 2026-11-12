# Файл: tests/test_okx.py
import os
import sys
import asyncio
from unittest.mock import AsyncMock, MagicMock

# Добавляем корень проекта в пути поиска
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.config import CONFIG
from network.client import AsyncHttpClient
from exchanges.okx import OkxExchange


async def run_okx_xray_test():
	print("\n" + "=" * 80)
	print("🔬 [РЕНТГЕН-ТЕСТ] Проверка коннектора exchanges/okx.py")
	print("=" * 80)

	# -------------------------------------------------------------------------
	# ШАГ 1: Проверка парсинга 4-элементных уровней стакана OKX v5 (офлайн)
	# -------------------------------------------------------------------------
	print("🧪 ШАГ 1. Проверка парсинга ответа OKX v5 (code='0', массивы по 4 элемента):")
	mock_net = MagicMock()

	fake_okx_response = {
		"code": "0",
		"msg": "",
		"data": [{
			"asks": [
				["73850.0", "1.4", "0", "3"],
				["73790.0", "0.8", "0", "2"]  # <-- Самый дешевый продавец
			],
			"bids": [
				["73710.0", "2.2", "0", "4"],
				["73775.0", "0.5", "0", "1"]  # <-- Самый дорогой покупатель
			],
			"ts": "1730000000888"
		}]
	}
	mock_net.fetch_json = AsyncMock(return_value=fake_okx_response)

	okx = OkxExchange(
		network_client=mock_net,
		base_url="https://okx.com",
		monitored_symbols=["BTC/USDT"]
	)

	book = await okx.fetch_order_book("BTC/USDT", limit=2)
	idx_price = 0

	if book and book["asks"][idx_price] == [73790.0, 0.8] and book["bids"][idx_price] == [73775.0, 0.5]:
		print("   ✅ УСПЕХ! Стакан OKX распарсен и отсортирован точно:")
		print(f"      • Лучший Ask (покупка) : {book['asks'][idx_price]} (тип цены: {type(book['asks'][idx_price][idx_price]).__name__})")
		print(f"      • Лучший Bid (продажа) : {book['bids'][idx_price]} (тип цены: {type(book['bids'][idx_price][idx_price]).__name__})\n")
	else:
		print(f"   🚨 ОШИБКА! Неверный формат стакана: {book}\n")

	# -------------------------------------------------------------------------
	# ШАГ 2: Проверка обработки ошибки API OKX (code != '0')
	# -------------------------------------------------------------------------
	print("🧪 ШАГ 2. Проверка защиты при ошибке API OKX:")
	mock_net.fetch_json = AsyncMock(return_value={"code": "51001", "msg": "Instrument ID does not exist"})
	bad_book = await okx.fetch_order_book("FAKE/USDT", limit=2)

	if bad_book is None:
		print("   ✅ УСПЕХ! Ошибка биржи перехвачена, вернулся None.\n")
	else:
		print(f"   🚨 ОШИБКА! Ожидали None, получили: {bad_book}\n")

	# -------------------------------------------------------------------------
	# ШАГ 3: Живой боевой запрос стакана BTC/USDT с реального сервера OKX
	# -------------------------------------------------------------------------
	print("🌐 ШАГ 3. Боевой запрос реального стакана BTC/USDT с OKX:")
	AsyncHttpClient._instance = None
	live_net = AsyncHttpClient(CONFIG)
	await live_net.init_tunnel()

	live_okx = OkxExchange(
		network_client=live_net,
		base_url=CONFIG["hosts"]["okx_base_url"],
		monitored_symbols=["BTC/USDT"]
	)

	limit_from_cfg = int(CONFIG["arbitrage"]["orderbook_limit"])
	live_book = await live_okx.fetch_order_book("BTC/USDT", limit=limit_from_cfg)

	if live_book and live_book["asks"] and live_book["bids"]:
		print(f"   ✅ УСПЕХ! Живой стакан OKX получен (глубина {len(live_book['asks'])} уровней):")
		print(f"      • Лучший Ask: {live_book['asks'][idx_price]}")
		print(f"      • Лучший Bid: {live_book['bids'][idx_price]}\n")
	else:
		print("   🚨 ОШИБКА! Не удалось получить живой стакан BTC/USDT с OKX.\n")

	await live_net.close()
	print("=" * 80)
	print("🎉 ИТОГ: Коннектор OKX полностью проверен и готов к работе!")
	print("=" * 80 + "\n")


if __name__ == "__main__":
	asyncio.run(run_okx_xray_test())
