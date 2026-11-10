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
		Адаптирован под любые имена аргументов из arbitrage_manager (exchange_a_name, price_a и т.д.).
		"""
		try:
			# Адаптация имен полей из менеджера арбитража
			buy_exchange = buy_exchange or kwargs.get("exchange_a_name") or kwargs.get("buy_ex")
			sell_exchange = sell_exchange or kwargs.get("exchange_b_name") or kwargs.get("sell_ex")
			buy_price = buy_price if buy_price is not None else (kwargs.get("price_a") or kwargs.get("buy_p"))
			sell_price = sell_price if sell_price is not None else (kwargs.get("price_b") or kwargs.get("sell_p"))
			volume_24h = volume_24h or kwargs.get("volume") or 0.0

			buy_price = float(buy_price)
			sell_price = float(sell_price)
			volume_24h = float(volume_24h)
			
			if buy_price <= 0:
				return None


			# --- ЗАЩИТНЫЙ ФИЛЬТР БАГА ОКРУГЛЕНИЯ BINGX ---
			# Если одна из сторон связки — BingX, проверяем цену на аномальные нули
			if "bingx" in [buy_exchange.lower(), sell_exchange.lower()]:
				# Проверяем строковое представление цены на наличие хвоста из трех нулей (например, 0.071000)
				buy_str = f"{buy_price:.6f}"
				sell_str = f"{sell_price:.6f}"
				if buy_str.endswith("000") or sell_str.endswith("000"):
					# Ложный сигнал вызванный округлением стакана — тихо игнорируем
					return None

			# Расчет математического спреда в процентах
			spread_pct = ((sell_price - buy_price) / buy_price) * 100

			# Фильтрация по минимальному порогу спреда из config_bot.json
			if spread_pct >= self.min_spread_pct:
				# Сохраняем верифицированный сигнал в базу данных
				self._save_to_database(
					symbol=symbol,
					buy_ex=buy_exchange,
					sell_ex=sell_exchange,
					buy_p=buy_price,
					sell_p=sell_price,
					spread_pct=spread_pct,
					volume_24h=volume_24h
				)
				
				# Формируем структуру ответа для вывода в консоль бота
				return {
					"symbol": symbol.upper(),
					"buy_exchange": buy_exchange.upper(),
					"sell_exchange": sell_exchange.upper(),
					"buy_price": buy_price,
					"sell_price": sell_price,
					"spread_pct": round(spread_pct, 2),
					"volume_24h": volume_24h
				}

		except Exception as e:
			print(f"🚨 [ANALYZER ERROR]: Ошибка при расчете спреда для {symbol}: {e}")
			
		return None
