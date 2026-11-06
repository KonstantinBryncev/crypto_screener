import os
import csv
import json
from database.storage import DBStorage


def load_config():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(base_dir, "config", "config_bot.json")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


INIT_DB_SQL = """
DROP TABLE IF EXISTS market_alerts CASCADE;

CREATE TABLE market_alerts (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP,
    alert_type TEXT,
    symbol TEXT,
    direction TEXT,
    delta_pct NUMERIC,
    main_metric TEXT,
    volume_info TEXT,
    info TEXT
);

CREATE TABLE IF NOT EXISTS asset_prices_history (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP,
    symbol TEXT,
    price NUMERIC
);

CREATE TABLE IF NOT EXISTS trade_signals (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP,
    symbol TEXT,
    signal_type TEXT,
    price NUMERIC,
    info TEXT
);
"""





def migrate():
    print("🚀 [ШАГ 1] Подключение к PostgreSQL и создание структуры таблиц...")
    config = load_config()
    
    # Жёстко зашиваем пароль для мигратора, чтобы не зависеть от JSON-файла сервера
    if "postgres" not in config:
        config["postgres"] = {}
    config["postgres"]["password"] = "CryptoDB_2026_Secure"
    config["postgres"]["dbname"] = "crypto_db"
    config["postgres"]["user"] = "postgres"
    config["postgres"]["host"] = "localhost"
    config["postgres"]["port"] = 5432
    
    storage = DBStorage(config)
    
    # Автоматически создаем таблицы в базе данных (Аналог Django migrate)
    conn = storage._get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(INIT_DB_SQL)
        conn.commit()
        print("✅ [УСПЕХ] Все таблицы (market_alerts, asset_prices_history, trade_signals) успешно созданы!")
    except Exception as e:
        conn.rollback()
        print(f"🚨 [ОШИБКА] Не удалось создать структуру БД: {e}")
        return
    finally:
        conn.close()
        
    # [ШАГ 2] Перенос старых аномалий из CSV
    signals_file = os.path.join("database", "signals_history.csv")
    if os.path.exists(signals_file):
        print(f"📦 [ШАГ 2] Чтение истории аномалий из {signals_file}...")
        with open(signals_file, "r", encoding="utf-8") as f:
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
        print(f"🎉 [МИГРАЦИЯ ЗАВЕРШЕНА] Успешно перенесено строк в базу: {count}")
    else:
        print("ℹ️ Старый файл истории сигналов не найден, создана пустая база данных.")

if __name__ == "__main__":
    migrate()
