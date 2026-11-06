import psycopg2
from psycopg2.extras import RealDictCursor

class DBStorage:
    def __init__(self, config):
        """Инициализация подключения к PostgreSQL на основе конфигурации"""
        self.db_config = config.get("postgres", {})
        
    def _get_connection(self):
        """Внутренний метод для создания чистого соединения с базой данных"""
        return psycopg2.connect(
            dbname=self.db_config.get("dbname", "crypto_db"),
            user=self.db_config.get("user", "postgres"),
            password=self.db_config.get("password", ""),
            host=self.db_config.get("host", "localhost"),
            port=self.db_config.get("port", 5432)
        )

    def save_possible_trade(self, symbol, buy_exchange, sell_exchange, buy_price, sell_price, spread_pct, volume_24h):
        """
        Сохраняет абсолютно все найденные ценовые аномалии в таблицу `possible_trades`
        для накопления 3-4 дневной статистики и последующего выбора ТОП-10 пар.
        """
        query = """
        INSERT INTO possible_trades (symbol, buy_exchange, sell_exchange, buy_price, sell_price, spread_pct, volume_24h)
        VALUES (%s, %s, %s, %s, %s, %s, %s);
        """
        conn = None
        try:
            conn = self._get_connection()
            with conn.cursor() as cur:
                cur.execute(query, (symbol, buy_exchange, sell_exchange, buy_price, sell_price, spread_pct, volume_24h))
            conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            print(f"🚨 [ОШИБКА БД] Не удалось сохранить статистику сделки: {e}")
        finally:
            if conn:
                conn.close()
