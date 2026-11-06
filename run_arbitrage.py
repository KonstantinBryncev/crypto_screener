import os
import sys
import time
import json
from datetime import datetime

# Импортируем наш собственный модуль для работы с PostgreSQL
from database.storage import DBStorage

def fetch_mock_ticker_data():
	"""
	Временная функция, которая имитирует получение реальных стаканов с 4 бирж.
	Возвращает структуру цен для демонстрации логики сравнения и фильтрации.
	"""
	return {
		"BTC/USDT": {
			"Bybit": {"buy_price": 68000.0, "sell_price": 68010.0, "volume_24h": 15000000},
			"KuCoin": {"buy_price": 68120.0, "sell_price": 68130.0, "volume_24h": 8000000},
			"OKX": {"buy_price": 67990.0, "sell_price": 68005.0, "volume_24h": 12000000},
			"Gate.io": {"buy_price": 68050.0, "sell_price": 68065.0, "volume_24h": 4000000}
		},
		"ETH/USDT": {
			"Bybit": {"buy_price": 2450.0, "sell_price": 2451.5, "volume_24h": 5000000},
			"KuCoin": {"buy_price": 2455.0, "sell_price": 2456.0, "volume_24h": 3000000},
			"OKX": {"buy_price": 2449.0, "sell_price": 2450.2, "volume_24h": 4500000},
			"Gate.io": {"buy_price": 2452.0, "sell_price": 2453.8, "volume_24h": 1200000}
		}
	}

def load_config():
	"""Загрузка конфигурационного файла из папки config"""
	base_dir = os.path.dirname(os.path.abspath(__file__))
	config_path = os.path.join(base_dir, "config", "config_bot.json")
	if os.path.exists(config_path):
		with open(config_path, "r", encoding="utf-8") as f:
			return json.load(f)
	return {}

def main():
	print("🟢 Запуск главного скрипта арбитражного скринера...")
	
	# Загружаем настройки из конфигурационного файла
	config = load_config()
	if not config:
		print("🚨 [ОШИБКА] Не удалось загрузить config_bot.json! Завершение работы.")
		sys.exit(1)
		
	# Инициализируем хранилище базы данных
	storage = DBStorage(config)
	
	# Безопасное извлечение настроек арбитража (Защита от KeyError)
	arbitrage_settings = config.get("arbitrage", config.get("arbitrage_settings", {}))
	min_spread_console = arbitrage_settings.get("min_spread_percent", 0.65)
	scan_delay_seconds = arbitrage_settings.get("scan_delay_seconds", 10.0)
	
	print(f"📊 Скринер запущен. Порог вывода возможных сделок в консоль: {min_spread_console}%")
	print(f"⏱️ Задержка между сканированиями: {scan_delay_seconds} сек.")
	print("Сбор общей статистики в таблицу possible_trades выполняется автоматически в фоне.\n")
	print("ВРЕМЯ\t\t\tПАРА\t\tНАПРАВЛЕНИЕ\t\tСПРЕД\tЦЕНЫ")
	print("-" * 90)

	while True:
		try:
			# Получаем свежие котировки по всем монетам и биржам
			market_data = fetch_mock_ticker_data()
			timestamp_now = datetime.now()
			timestamp_str = timestamp_now.strftime("%Y-%m-%d %H:%M:%S")

			# Перебираем каждую торговую пару (например, BTC/USDT)
			for symbol, exchanges in market_data.items():
				
				# Ищем самую выгодную биржу для покупки (минимальная цена продажи sell_price)
				buy_exchange = min(exchanges, key=lambda e: exchanges[e]["sell_price"])
				buy_price = exchanges[buy_exchange]["sell_price"]
				
				# Ищем самую выгодную биржу для продажи (максимальная цена покупки buy_price)
				sell_exchange = max(exchanges, key=lambda e: exchanges[e]["buy_price"])
				sell_price = exchanges[sell_exchange]["buy_price"]
				
				# Берем суточный объем по паре для фильтрации ликвидности
				volume_24h = exchanges[buy_exchange]["volume_24h"]

				# Проверяем, что покупка и продажа происходят на разных биржах
				if buy_exchange != sell_exchange:
					
					# Рассчитываем грязный процент межбиржевого спреда
					spread_pct = ((sell_price - buy_price) / buy_price) * 100

					# Если спред положительный — фиксируем потенциальный арбитраж
					if spread_pct > 0:
						
						# 1. ОТПРАВЛЯЕМ АБСОЛЮТНО ВСЕ СИГНАЛЫ В БАЗУ ДАННЫХ ДЛЯ СБОРА ТОП-10 ПАР
						try:
							storage.save_possible_trade(
								symbol=symbol,
								buy_exchange=buy_exchange,
								sell_exchange=sell_exchange,
								buy_price=buy_price,
								sell_price=sell_price,
								spread_pct=round(spread_pct, 4),
								volume_24h=volume_24h
							)
						except Exception as db_err:
							# Предотвращаем падение главного цикла при сбоях сети СУБД
							pass

						# 2. ФИЛЬТРУЕМ ВЫВОД В КОНСОЛЬ: Показываем только жирные возможные сделки
						if spread_pct >= min_spread_console:
							# Вывод в консоль со звуковым сигналом \a
							print(f"💰\t[{timestamp_str}]\t{symbol}\t{buy_exchange} ➔ {sell_exchange}\t{spread_pct:.2f}%\t{buy_price} ➔ {sell_price}\a")

			# Задержка между циклами сканирования рынка
			time.sleep(scan_delay_seconds)

		except KeyboardInterrupt:
			print("\n🛑 Скринер остановлен пользователем.")
			break
		except Exception as e:
			print(f"🚨 [СИСТЕМНАЯ ОШИБКА В ЦИКЛЕ]: {e}")
			time.sleep(5)

if __name__ == "__main__":
	main()
