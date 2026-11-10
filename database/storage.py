import psycopg2
from psycopg2.extras import Json
from datetime import datetime

class DBStorage:
    """
    Менеджер для работы с СУБД PostgreSQL.
    Отвечает за подключение, создание таблиц и запись результатов.
    """
    def __init__(self, db_settings: dict):
        self.config = db_settings.get("postgres", {})

    def _get_connection(self):
        # Жестко форсим dbname на crypto_db, если в конфиге пусто, чтобы не улетать в дефолтную базу postgres
        return psycopg2.connect(
            dbname=self.config.get("dbname", "crypto_db"),
            user=self.config.get("user", "postgres"),
            password=self.config.get("password", "CryptoDB_2026_Secure"),
            host=self.config.get("host", "127.0.0.1"),
            port=self.config.get("port", 5432)
        )

    def save_possible_trade(self, symbol, buy_exchange, sell_exchange, buy_price, sell_price, spread_pct, volume_24h=0.0):
        """
        Запись найденной арбитражной ситуации в таблицу possible_trades с учетом объема.
        """
        sql = """
            INSERT INTO possible_trades 
            (timestamp, symbol, buy_exchange, sell_exchange, buy_price, sell_price, spread_pct, volume_24h)
            VALUES (CURRENT_TIMESTAMP, %s, %s, %s, %s, %s, %s, %s);
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, (
                    symbol.upper(),
                    buy_exchange.lower(),
                    sell_exchange.lower(),
                    float(buy_price),
                    float(sell_price),
                    float(spread_pct),
                    float(volume_24h)
                ))
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"🚨 [DB ERROR]: Не удалось записать сделку: {e}")
        finally:
            conn.close()
