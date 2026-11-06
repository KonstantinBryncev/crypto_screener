import os
import json
import psycopg2
from database.storage import DBStorage

# Новая структура базы данных под межбиржевой арбитраж и сбор статистики
INIT_DB_SQL = """
DROP TABLE IF EXISTS possible_trades CASCADE;
DROP TABLE IF EXISTS virtual_balances CASCADE;
DROP TABLE IF EXISTS crypto_commissions CASCADE;
DROP TABLE IF EXISTS virtual_orders CASCADE;

-- 1. Таблица для сбора статистики и поиска ТОП-10 самых активных пар
CREATE TABLE possible_trades (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    symbol TEXT,
    buy_exchange TEXT,
    sell_exchange TEXT,
    buy_price NUMERIC,
    sell_price NUMERIC,
    spread_pct NUMERIC,
    volume_24h NUMERIC
);

-- 2. Виртуальные балансы на биржах для будущих тестов экономики
CREATE TABLE virtual_balances (
    id SERIAL PRIMARY KEY,
    exchange_name TEXT,
    asset TEXT,
    balance_total NUMERIC DEFAULT 0.0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Справочник торговых и сетевых комиссий (для второго бота-бухгалтера)
CREATE TABLE crypto_commissions (
    id SERIAL PRIMARY KEY,
    exchange_name TEXT,
    symbol TEXT,
    trade_fee_pct NUMERIC DEFAULT 0.1,
    network_fee TEXT
);

-- 4. История совершенных симуляционных сделок
CREATE TABLE virtual_orders (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    symbol TEXT,
    buy_exchange TEXT,
    sell_exchange TEXT,
    amount NUMERIC,
    buy_price NUMERIC,
    sell_price NUMERIC,
    net_profit_usdt NUMERIC
);
"""

def load_config():
    """Загрузка конфигурационного файла бота для получения параметров СУБД"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(base_dir, "config", "config_bot.json")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def migrate():
    """Основная функция для пересоздания структуры таблиц в PostgreSQL"""
    print("🚀 [ШАГ 1] Подключение к PostgreSQL...")
    config = load_config()
    storage = DBStorage(config)
    
    try:
        conn = storage._get_connection()
    except Exception as conn_err:
        print(f"🚨 ОШИБКА ПОДКЛЮЧЕНИЯ К СУБД: {conn_err}")
        print("Убедись, что параметры в config_bot.json верны.")
        return

    print("🛠️ [ШАГ 2] Сброс старых таблиц и создание новой структуры...")
    try:
        with conn.cursor() as cur:
            cur.execute(INIT_DB_SQL)
        conn.commit()
        print("✅ [УСПЕХ] Новая структура базы успешно развернута!")
        print("Таблица possible_trades полностью готова к накоплению статистики.")
    except Exception as e:
        conn.rollback()
        print(f"🚨 [ОШИБКА] Не удалось выполнить SQL-скрипт структуры: {e}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()

if __name__ == "__main__":
    migrate()
