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
    print("🚀 Старт миграции радара Bybit в PostgreSQL...")
    config = load_config()
    storage = DBStorage(config)
    
    signals_file = os.path.join("database", "signals_history.csv")
    balance_file = os.path.join("database", "balance_history.csv")
    
    # 1. Миграция алертов волатильности/объема
    if os.path.exists(signals_file):
        print(f"📦 Обработка {signals_file}...")
        with open(signals_file, "r", encoding="utf-8") as f:
            # Указываем разделитель ';' как в твоем файле
            reader = csv.DictReader(f, delimiter=';')
            count = 0
            for row in reader:
                storage.save_alert(
                    ts=row.get("Timestamp"),
                    alert_type=row.get("Type"),
                    symbol=row.get("Symbol"),
                    direction=row.get("Direction"),
                    delta=float(row.get("Delta_Pct", 0)),
                    metric=row.get("Main_Metric", ""),
                    info=row.get("Volume_Info", "")
                )
                count += 1
        print(f"✅ Перенесено рыночных алертов: {count}")

    # 2. Миграция балансов
    if os.path.exists(balance_file):
        print(f"📦 Обработка {balance_file}...")
        with open(balance_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=';')
            count = 0
            for row in reader:
                storage.save_balance(
                    ts=row.get("Timestamp"),
                    balance=float(row.get("Balance_USDT", 0))
                )
                count += 1
        print(f"✅ Перенесено записей баланса: {count}")

if __name__ == "__main__":
    migrate()
