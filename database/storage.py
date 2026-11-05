# Модуль: database/storage.py
import psycopg2
from datetime import datetime

class DBStorage:
    def __init__(self, db_settings: dict):
        self.config = db_settings.get("postgres", {})
        
    def _get_connection(self):
        return psycopg2.connect(
            dbname=self.config.get("dbname", "crypto_db"),
            user=self.config.get("user", "postgres"),
            password=self.config.get("password", ""),
            host=self.config.get("host", "localhost"),
            port=self.config.get("port", 5432)
        )

    def save_balance(self, ts, balance: float):
        """Запись лога баланса"""
        sql = "INSERT INTO balance_logs (timestamp, balance_usdt) VALUES (%s, %s);"
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, (ts, balance))
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"🚨 [DB ERROR] Баланс: {e}")
        finally:
            conn.close()

    def save_alert(self, ts, alert_type, symbol, direction, delta, metric, info):
        """Запись всплеска объема или волатильности"""
        sql = """
            INSERT INTO market_alerts 
            (timestamp, alert_type, symbol, direction, delta_pct, main_metric, volume_info)
            VALUES (%s, %s, %s, %s, %s, %s, %s);
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, (ts, alert_type, symbol, direction, delta, metric, info))
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"🚨 [DB ERROR] Алерт: {e}")
        finally:
            conn.close()
