# Модуль: database/storage.py
import psycopg2
from psycopg2.extras import Json
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

    def save_alert(self, ts, alert_type, symbol, direction, delta, metric, info):
        """Запись аномалий объема и волатильности (market_alerts)"""
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
            print(f"🚨 [DB ALERT ERROR]: {e}")
        finally:
            conn.close()

    def save_asset_price(self, symbol: str, exchange: str, price: float, ch_5m: float, ch_1h: float, vol_24h: float):
        """Запись исторических изменений цен отслеживаемых монет (asset_prices_history)"""
        sql = """
            INSERT INTO asset_prices_history 
            (timestamp, symbol, exchange, current_price, change_pct_5m, change_pct_1h, volume_24h)
            VALUES (%s, %s, %s, %s, %s, %s, %s);
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, (datetime.utcnow(), symbol, exchange, price, ch_5m, ch_1h, vol_24h))
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"🚨 [DB PRICE ERROR]: {e}")
        finally:
            conn.close()

    def save_trade_signal(self, strategy: str, symbol: str, buy_ex: str, sell_ex: str, profit: float, conditions: dict):
        """Запись потенциальных торговых сделок для анализа частоты (trade_signals)"""
        sql = """
            INSERT INTO trade_signals 
            (timestamp, strategy_name, symbol, buy_exchange, sell_exchange, potential_profit_pct, trigger_conditions)
            VALUES (%s, %s, %s, %s, %s, %s, %s);
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, (datetime.utcnow(), strategy, symbol, buy_ex, sell_ex, profit, Json(conditions)))
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"🚨 [DB SIGNAL ERROR]: {e}")
        finally:
            conn.close()
