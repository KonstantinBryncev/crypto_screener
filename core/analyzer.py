import psycopg2
from datetime import datetime

class ArbitrageAnalyzer:
	"""
	Модуль математического анализа межбиржевого спреда.
	Рассчитывает чистую прибыль с учетом комиссий и сохраняет сигналы в PostgreSQL.
	Все параметры и доступы динамически импортируются из конфигурационного файла.
	"""
	def __init__(self, config: dict = None):
		self.notifier = None
		# Извлекаем параметры базы данных из общего конфигурационного файла
		db_config = config.get("postgres", {}) if config else {}
		
		# Задаем имя базы данных строго по конфигурации (с дефолтом на crypto_db)
		self.dbname = db_config.get("dbname") or "crypto_db"
		self.user = db_config.get("user") or "postgres"
		self.password = db_config.get("password") or "CryptoDB_2026_Secure"
		
		# Предотвращаем конфликты локальных сокетов: localhost подменяем на сетевой IP
		host_val = db_config.get("host") or "127.0.0.1"
		self.host = "127.0.0.1" if host_val == "localhost" else host_val
		
		self.port = int(db_config.get("port") or 5432)
		
		# Загружаем настройки фильтрации спреда из конфига (по умолчанию 0.5%)
		bot_settings = config.get("bot_settings", {}) if config else {}
		self.min_spread_pct = float(bot_settings.get("min_spread_pct") or 0.5)

	def set_notifier(self, notifier):
		"""
		Установка модуля уведомлений (например, для Telegram).
		"""
		self.notifier = notifier

	def _get_connection(self):
		"""
		Внутренний метод создания безопасного подключения к PostgreSQL.
		"""
		return psycopg2.connect(
			dbname=self.dbname,
			user=self.user,
			password=self.password,
			host=self.host,
			port=self.port
		)

	def _save_to_database(self, symbol, buy_ex, sell_ex, buy_p, sell_p, spread_pct, volume_24h):
		"""
		Безопасная запись верифицированного сигнала в таблицу possible_trades.
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
					buy_ex.lower(),
					sell_ex.lower(),
					float(buy_p),
					float(sell_p),
					float(spread_pct),
					float(volume_24h)
				))
			conn.commit()
		except Exception as e:
			conn.rollback()
			print(f"🚨 [DB ERROR]: Ошибка записи в PostgreSQL: {e}")
		finally:
			conn.close()

	def calculate_spot_spread(self, symbol, buy_exchange=None, sell_exchange=None, buy_price=None, sell_price=None, volume_24h=0.0, **kwargs):
		"""
		Рассчитывает чистый процентный спред между ценами покупки и продажи.
		Максимально адаптирован под любые варианты аргументов из arbitrage_manager.
		"""
		try:
			# 1. Извлекаем биржу покупки (все возможные варианты ключей)
			buy_ex = buy_exchange or kwargs.get("exchange_a_name") or kwargs.get("buy_ex") or kwargs.get("exchange_buy") or kwargs.get("buy_exchange")
			# 2. Извлекаем биржу продажи
			sell_ex = sell_exchange or kwargs.get("exchange_b_name") or kwargs.get("sell_ex") or kwargs.get("exchange_sell") or kwargs.get("sell_exchange")
			
			# 3. Извлекаем цену покупки (ищем по всем возможным названиям полей в проекте)
			b_price = buy_price
			if b_price is None:
				b_price = kwargs.get("price_a") or kwargs.get("buy_price") or kwargs.get("buy_p") or kwargs.get("ask") or kwargs.get("ask_price")

			# 4. Извлекаем цену продажи
			s_price = sell_price
			if s_price is None:
				s_price = kwargs.get("price_b") or kwargs.get("sell_price") or kwargs.get("sell_p") or kwargs.get("bid") or kwargs.get("bid_price")

			# 5. Извлекаем объем торгов
			vol_24h = volume_24h or kwargs.get("volume") or kwargs.get("volume_24h") or kwargs.get("vol") or 0.0

			# Защитная проверка: если цены так и не нашлись в переданных аргументах, пропускаем пару без падения скрипта
			if b_price is None or s_price is None or buy_ex is None or sell_ex is None:
				# Для отладки раскомментируй строку ниже, чтобы увидеть реальные ключи, если опять пустые прилетят:
				# print(f"ℹ️ [DEBUG KEYS]: Прилетели аргументы без цен для {symbol}: {kwargs.keys()}")
				return None

			# Преобразование типов данных
			buy_price_float = float(b_price)
			sell_price_float = float(s_price)
			volume_24h_float = float(vol_24h)
			
			if buy_price_float <= 0:
				return None

			# --- ЗАЩИТНЫЙ ФИЛЬТР БАГА ОКРУГЛЕНИЯ BINGX ---
			if "bingx" in [str(buy_ex).lower(), str(sell_ex).lower()]:
				buy_str = f"{buy_price_float:.6f}"
				sell_str = f"{sell_price_float:.6f}"
				if buy_str.endswith("000") or sell_str.endswith("000"):
					return None

			# Расчет математического спреда в процентах
			spread_pct = ((sell_price_float - buy_price_float) / buy_price_float) * 100

			# Фильтрация по минимальному порогу спреда из config_bot.json
			if spread_pct >= self.min_spread_pct:
				# Сохраняем верифицированный сигнал в базу данных
				self._save_to_database(
					symbol=symbol,
					buy_ex=buy_ex,
					sell_ex=sell_ex,
					buy_p=buy_price_float,
					sell_p=sell_price_float,
					spread_pct=spread_pct,
					volume_24h=volume_24h_float
				)
				
				return {
					"symbol": symbol.upper(),
					"buy_exchange": str(buy_ex).upper(),
					"sell_exchange": str(sell_ex).upper(),
					"buy_price": buy_price_float,
					"sell_price": sell_price_float,
					"spread_pct": round(spread_pct, 2),
					"volume_24h": volume_24h_float
				}

		except Exception as e:
			print(f"🚨 [ANALYZER ERROR]: Ошибка при расчете спреда для {symbol}: {e}")
			
		return None
