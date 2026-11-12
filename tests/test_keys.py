# Файл: tests/test_keys.py
import os
import sys
import asyncio
import json

# Добавляем корень проекта в пути поиска, чтобы скрипт видел папки config, exchanges и network
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.config import CONFIG
from network.client import AsyncHttpClient
from exchanges.bybit import BybitExchange
from exchanges.bingx import BingXExchange
from exchanges.kucoin import KuCoinExchange
from exchanges.gate import GateExchange
from exchanges.okx import OkxExchange

async def check_all_keys():
	print("\n" + "="*60)
	print("🔑 [ТЕСТ API-КЛЮЧЕЙ] Начинаем проверку доступа к биржам...")
	print("="*60)
	
	# Инициализируем сетевой клиент (пока без VPN, в чистом режиме)
	net_client = AsyncHttpClient(CONFIG)
	hosts = CONFIG.get("hosts", {})
	exchanges_cfg = CONFIG.get("exchanges", {})
	
	mapping = {
		"bybit": BybitExchange,
		"bingx": BingXExchange,
		"kucoin": KuCoinExchange,
		"gate": GateExchange,
		"okx": OkxExchange
	}
	
	for exch_id, exch_class in mapping.items():
		creds = exchanges_cfg.get(exch_id, {})
		url = hosts.get(f"{exch_id}_base_url")
		
		print(f"\n--- Проверка [{exch_id.upper()}] ---")
		
		# 1. Базовая проверка, что строки в config.py вообще заполнены
		if not creds.get("api_key") or not creds.get("api_secret"):
			print(f" ⚠️  [ПРОПУСК] В config.py не заполнены api_key или api_secret!")
			continue
			
		print(f" -> Ключи в конфиге найдены (длина key: {len(creds['api_key'])} симв.).")
		
		# 2. Собираем коннектор
		kwargs = {
			"network_client": net_client,
			"base_url": url,
			"monitored_symbols": ["BTC/USDT"],
			"api_key": creds["api_key"],
			"api_secret": creds["api_secret"]
		}
		if "passphrase" in creds:
			kwargs["api_passphrase"] = creds["passphrase"]
			
		connector = exch_class(**kwargs)
		
		# 3. Пробуем инициализировать сессию и дернуть публичный/приватный метод
		try:
			await connector.init_exchange()
			# Пробуем получить стакан как базовую проверку связи
			ob = await connector.fetch_order_book("BTC/USDT", limit=1)
			if ob and (ob.get("asks") or ob.get("bids")):
				print(f"{json.dumps(ob.get('asks'), indent='\t', ensure_ascii=False)}")
				print(f"{json.dumps(ob.get('bids'), indent='\t', ensure_ascii=False)}")
				print(f" ✅ [СВЯЗЬ ОК] Биржа ответила, данные получены!")
			else:
				print(f" ⚠️  [ПУСТОЙ ОТВЕТ] Соединение прошло, но стакан пуст (возможно, нужен VPN).")
		except Exception as e:
			print(f" 🚨 [ОШИБКА] Сбой при обращении к {exch_id.upper()}: {e}")

	if hasattr(net_client, "close"):
		await net_client.close()
	elif hasattr(net_client, "session") and net_client.session:
		await net_client.session.close()

	print("\n" + "="*60)
	print("🏁 Проверка завершена.")
	print("="*60 + "\n")

if __name__ == "__main__":
	asyncio.run(check_all_keys())
