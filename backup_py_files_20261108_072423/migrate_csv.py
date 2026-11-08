import os
import json
from database.storage import DBStorage

INIT_DB_SQL = """
DROP TABLE IF EXISTS possible_trades CASCADE;

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
"""

def load_config():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(base_dir, "config", "config_bot.json")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def migrate():
    print("🚀 [ШАГ 1] Подключение к PostgreSQL для создания чистой структуры радара...")
    config = load_config()
    if not config:
        print("🚨 [ОШИБКА] Не найден файл конфигурации config_bot.json")
        return
        
    storage = DBStorage(config)
    try:
        conn = storage._get_connection()
    except Exception as conn_err:
        print(f"🚨 ОШИБКА ПОДКЛЮЧЕНИЯ К СУБД: {conn_err}")
        print("Проверь, работает ли сервер PostgreSQL и верен ли пароль в конфиге!")
        return

    try:
        with conn.cursor() as cur:
            cur.execute(INIT_DB_SQL)
        conn.commit()
        print("✅ [УСПЕХ] Таблица possible_trades успешно пересоздана в режиме чистой базы!")
    except Exception as e:
        conn.rollback()
        print(f"🚨 [ОШИБКА] Не удалось обновить структуру таблиц: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
