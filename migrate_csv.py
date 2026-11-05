# Файл в корне проекта: migrate_csv.py
import os
import csv
import json
import psycopg2
from database.storage import DBStorage

# Тот самый SQL-код структуры таблиц, теперь он создаётся автоматически!
INIT_DB_SQL = """
CREATE TABLE IF NOT EXISTS market_alerts (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    alert_type VARCHAR(20) NOT NULL,
    symbol VARCHAR(30) NOT NULL,
    direction VARCHAR(50) NOT NULL,
    delta_pct NUMERIC(12, 4) NOT NULL,
    main_metric TEXT NOT NULL,
    volume_info TEXT
);

CREATE TABLE IF NOT EXISTS asset_prices_history (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    symbol VARCHAR(30) NOT NULL,
    exchange VARCHAR(30) NOT NULL,
    current_price NUMERIC(20, 10) NOT NULL,
    change_pct_5m NUMERIC(6, 3),
    change_pct_1h NUMERIC(6, 3),
    volume_24h NUMERIC(24, 4)
);

CREATE TABLE IF NOT EXISTS trade_signals (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    strategy_name VARCHAR(50) NOT NULL,
    symbol VARCHAR(30) NOT NULL,
    buy_exchange VARCHAR(30) NOT NULL,
    sell_exchange VARCHAR(30) DEFAULT NULL,
    potential_profit_pct NUMERIC(6, 3),
    status VARCHAR(20) DEFAULT 'SIGNAL',
    trigger_conditions JSONB
);

CREATE INDEX IF NOT EXISTS idx_alerts_ts ON market_alerts(timestamp);
CREATE INDEX IF NOT EXISTS idx_prices_ts_sym ON asset_prices_history(timestamp, symbol);
CREATE INDEX IF NOT EXISTS idx_signals_strat_ts ON trade_signals(strategy_name, timestamp);
"""

def load_config():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(base_dir, "config", "config_bot.json")
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)

def migrate():
    print("🚀 [ШАГ 1] Подключение к PostgreSQL и создание структуры таблиц...")
    config = load_config()
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
