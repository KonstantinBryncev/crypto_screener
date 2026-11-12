# Файл: database/db_manager.py
import logging
import psycopg2

logger = logging.getLogger("DatabaseManager")


class DatabaseManager:
	"""
	Единый централизованный менеджер для работы с PostgreSQL во всем проекте.
	Все остальные модули обращаются к базе только через этот класс.
	"""
	def __init__(self, config: dict):
		if not config:
			raise ValueError("🚨 [DB] В DatabaseManager передан пустой словарь конфигурации!")

		# Строго вычитываем параметры подключения из секции 'postgres' без хардкода
		try:
			db_config = config["postgres"]
			self.dbname = str(db_config["dbname"])
			self.user = str(db_config["user"])
			self.password = str(db_config["password"])
			
			host_val = str(db_config["host"])
			self.host = "127.0.0.1" if host_val == "localhost" else host_val
			self.port = int(db_config["port"])
			self.connect_timeout = int(db_config["connect_timeout"])
		except KeyError as e:
			raise ValueError(f"🚨 [КОНФИГ] В секции 'postgres' отсутствует обязательный ключ: {e}")

	def get_connection(self):
		"""Создает и возвращает новое подключение к PostgreSQL."""
		return psycopg2.connect(
			dbname=self.dbname,
			user=self.user,
			password=self.password,
			host=self.host,
			port=self.port,
			connect_timeout=self.connect_timeout
		)

	def init_tables(self):
		"""
		Проверяет наличие необходимых таблиц в базе и создает их при первом запуске.
		Удобно при переезде на новый сервер или чистую базу.
		"""
		create_sql = """
			CREATE TABLE IF NOT EXISTS possible_trades (
				id SERIAL PRIMARY KEY,
				timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
				symbol VARCHAR(32) NOT NULL,
				buy_exchange VARCHAR(32) NOT NULL,
				sell_exchange VARCHAR(32) NOT NULL,
				buy_price NUMERIC(20, 8) NOT NULL,
				sell_price NUMERIC(20, 8) NOT NULL,
				spread_pct NUMERIC(10, 4) NOT NULL,
				volume_24h NUMERIC(20, 2) NOT NULL
			);
		"""
		conn = None
		try:
			conn = self.get_connection()
			with conn.cursor() as cur:
				cur.execute(create_sql)
			conn.commit()
			logger.info("✅ [DB] Таблица possible_trades проверена/готова к работе.")
		except Exception as e:
			logger.error(f"🚨 [DB ERROR] Не удалось инициализировать таблицы в PostgreSQL: {e}")
			print(f"🚨 [DB ERROR]: Не удалось инициализировать таблицы: {e}", flush=True)
		finally:
			if conn:
				conn.close()

	def save_possible_trade(self, symbol: str, buy_ex: str, sell_ex: str, buy_p: float, sell_p: float, spread_pct: float, volume_24h: float):
		"""Записывает найденную арбитражную связку в таблицу possible_trades."""
		sql = """
			INSERT INTO possible_trades 
			(timestamp, symbol, buy_exchange, sell_exchange, buy_price, sell_price, spread_pct, volume_24h)
			VALUES (CURRENT_TIMESTAMP, %s, %s, %s, %s, %s, %s, %s);
		"""
		conn = None
		try:
			conn = self.get_connection()
			with conn.cursor() as cur:
				cur.execute(sql, (
					symbol.upper(),
					buy_ex.lower(),
					sell_ex.lower(),
					float(buy_p),
					float(sell_p),
					float(spread_pct),
					float(volume_24h)
				))
			conn.commit()
		except Exception as e:
			logger.error(f"🚨 [DB ERROR] Ошибка записи связки {symbol} в PostgreSQL: {e}")
			print(f"🚨 [DB ERROR]: Ошибка записи в PostgreSQL: {e}", flush=True)
		finally:
			if conn:
				conn.close()
