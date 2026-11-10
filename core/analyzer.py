# Файл: core/analyzer.py
import psycopg2
from datetime import datetime

class ArbitrageAnalyzer:
	"""
	Модуль математического анализа межбиржевого спреда.
	Автоматически распаковывает стаканы бирж, ищет дельту и пишет логи в PostgreSQL.
	"""
	def __init__(self, config: dict = None):
		self.notifier = None
		db_config = config.get("postgres", {}) if config else {}
		
		self.dbname = db_config.get("dbname") or "crypto_db"
		self.user = db_config.get("user") or "postgres"
		self.password = db_config.get("password") or "CryptoDB_2026_Secure"
		
		host_val = db_config.get("host") or "127.0.0.1"
		self.host = "127.0.0.1" if host_val == "localhost" else host_val
		self.port = int(db_config.get("port") or 5432)
		
		arb_settings = config.get("arbitrage", {}) if config else {}
		self.min_spread_pct = float(arb_settings.get("min_spread_percent") or -1.0)

	def set_notifier(self, notifier):
		self.notifier = notifier

	def _get_connection(self):
		return psycopg2.connect(
			dbname=self.dbname, user=self.user, password=self.password, host=self.host, port=self.port
		)

	def _save_to_database(self, symbol, buy_ex, sell_ex, buy_p, sell_p, spread_pct, volume_24h):
		sql = """
			INSERT INTO possible_trades 
			(timestamp, symbol, buy_exchange, sell_exchange, buy_price, sell_price, spread_pct, volume_24h)
			VALUES (CURRENT_TIMESTAMP, %s, %s, %s, %s, %s, %s, %s);
		"""
		try:
			conn = self._get_connection()
			with conn.cursor() as cur:
				cur.execute(sql, (
					symbol.upper(), buy_ex.lower(), sell_ex.lower(),
					float(buy_p), float(sell_p), float(spread_pct), float(volume_24h)
				))
			conn.commit()
			conn.close()
		except Exception as e:
			print(f"🚨 [DB ERROR]: Ошибка записи в PostgreSQL: {e}")

	async def calculate_spot_spread(self, symbol, **kwargs):
		"""Распаковывает унифицированные стаканы из kwargs и считает чистый спред"""
		try:
			ex_a_name = kwargs.get("exchange_a_name")
			ex_b_name = kwargs.get("exchange_b_name")
			ob_a = kwargs.get("orderbook_a")
			ob_b = kwargs.get("orderbook_b")
			vol_24h = float(kwargs.get("volume_24h") or 0.0)
			filter_threshold = kwargs.get("min_spread_pct", self.min_spread_pct)

			if not ob_a or not ob_b or not ex_a_name or not ex_b_name:
				return {}

			# Вытаскиваем лучшие цены из стаканов (Лучшая продажа / Лучшая покупка)
			asks_a = ob_a.get("asks", [])
			bids_a = ob_a.get("bids", [])
			asks_b = ob_b.get("asks", [])
			bids_b = ob_b.get("bids", [])

			if not asks_a or not bids_a or not asks_b or not bids_b:
				return {}

			best_ask_a = float(asks_a[0][0])
			best_bid_a = float(bids_a[0][0])
			best_ask_b = float(asks_b[0][0])
			best_bid_b = float(bids_b[0][0])

			# Направление 1: Покупаем на А -> Продаем на Б
			spread_1 = ((best_bid_b - best_ask_a) / best_ask_a) * 100
			# Направление 2: Покупаем на Б -> Продаем на А
			spread_2 = ((best_bid_a - best_ask_b) / best_ask_b) * 100

			final_res = {}
			if spread_1 >= filter_threshold and spread_1 > spread_2:
				final_res = {
					"symbol": symbol.upper(), "buy_exchange": str(ex_a_name).upper(), "sell_exchange": str(ex_b_name).upper(),
					"buy_price": best_ask_a, "sell_price": best_bid_b, "spread_pct": round(spread_1, 3), "volume_24h": vol_24h
				}
			elif spread_2 >= filter_threshold:
				final_res = {
					"symbol": symbol.upper(), "buy_exchange": str(ex_b_name).upper(), "sell_exchange": str(ex_a_name).upper(),
					"buy_price": best_ask_b, "sell_price": best_bid_a, "spread_pct": round(spread_2, 3), "volume_24h": vol_24h
				}

			if final_res:
				# Пишем лог в СУБД Postgres
				self._save_to_database(
					symbol=final_res["symbol"], buy_ex=final_res["buy_exchange"], sell_ex=final_res["sell_exchange"],
					buy_p=final_res["buy_price"], sell_p=final_res["sell_price"], spread_pct=final_res["spread_pct"], volume_24h=final_res["volume_24h"]
				)
				return final_res

		except Exception as e:
			print(f"🚨 [ANALYZER ERROR]: Сбой расчета спреда для {symbol}: {e}")
			
		return {}
