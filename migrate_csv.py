# Файл в корне проекта: migrate_csv.py
import os
import csv
import json
from database.storage import DBStorage

def load_config():
	base_dir = os.path.dirname(os.path.abspath(__file__))
	config_path = os.path.join(base_dir, "config", "config_bot.json")
	with open(config_path, "r", encoding="utf-8") as f:
		return json.load(f)

def migrate():
	print("🚀 Запуск миграции старых данных из CSV в PostgreSQL...")
	config = load_config()
	storage = DBStorage(config)
	
	signals_file = os.path.join("database", "signals_history.csv")
	balance_file = os.path.join("database", "balance_history.csv")
	
	# 1. Миграция сигналов
	if os.path.exists(signals_file):
		print(f"📦 Чтение {signals_file}...")
		with open(signals_file, "r", encoding="utf-8") as f:
			reader = csv.DictReader(f)
			count = 0
			for row in reader:
				# Приводим типы из строк CSV в нужные типы для БД
				data = {
					"token_symbol": row.get("token_symbol"),
					"buy_exchange": row.get("buy_exchange"),
					"buy_price": float(row.get("buy_price", 0)),
					"buy_initial_volume": float(row.get("buy_initial_volume", 0)),
					"buy_fee_rate": float(row.get("buy_fee_rate", 0.001)),
					"sell_exchange": row.get("sell_exchange"),
					"sell_price": float(row.get("sell_price", 0)),
					"sell_initial_volume": float(row.get("sell_initial_volume", 0)),
					"sell_fee_rate": float(row.get("sell_fee_rate", 0.001)),
					"raw_spread_percent": float(row.get("raw_spread_percent", 0)),
					"net_profit_usdt": float(row.get("net_profit_usdt", 0)),
					"max_executable_volume": float(row.get("max_executable_volume", 0)),
					"is_deposit_enabled": row.get("is_deposit_enabled") == "True",
					"is_withdrawal_enabled": row.get("is_withdrawal_enabled") == "True",
					"network_name": row.get("network_name", "Unknown")
				}
				storage.save_signal(data)
				count += 1
		print(f"✅ Успешно перенесено сигналов: {count}")

	# 2. Миграция балансов
	if os.path.exists(balance_file):
		print(f"📦 Чтение {balance_file}...")
		with open(balance_file, "r", encoding="utf-8") as f:
			reader = csv.DictReader(f)
			count = 0
			for row in reader:
				try:
					details = json.loads(row.get("details", "{}"))
				except:
					details = {}
				storage.save_balance(
					total=float(row.get("total_balance_usdt", 0)),
					available=float(row.get("available_balance_usdt", 0)),
					in_orders=float(row.get("in_orders_usdt", 0)),
					details_dict=details
				)
				count += 1
		print(f"✅ Успешно перенесено логов баланса: {count}")

if __name__ == "__main__":
	migrate()
