# Файл: core/analyzer.py
import logging
from database.db_manager import DatabaseManager

logger = logging.getLogger("ArbitrageAnalyzer")


class ArbitrageAnalyzer:
	"""
	Модуль математического анализа межбиржевого спреда.
	Считает средневзвешенную цену по глубине стаканов, вычитает комиссии
	и передает валидные связки в единый DatabaseManager.
	"""
	def __init__(self, config: dict):
		if not config:
			raise ValueError("🚨 [ANALYZER] Передан пустой словарь конфигурации!")

		# Подключаем единый менеджер базы данных вместо дублирования кода БД
		self.db = DatabaseManager(config)

		# Строго загружаем пороги спредов, комиссию и объем сделки из секции 'arbitrage'
		try:
			arb_settings = config["arbitrage"]
			self.min_spread_pct = float(arb_settings["min_spread_percent"])
			self.max_spread_pct = float(arb_settings["max_spread_percent"])
			self.trade_fee_pct = float(arb_settings["trade_fee_percent"])
			self.base_order_usdt = float(arb_settings["base_order_usdt"])
		except KeyError as e:
			raise ValueError(f"🚨 [КОНФИГ] В секции 'arbitrage' отсутствует обязательный ключ: {e}")


	def _get_connection(self):
		# Открываем соединение с PostgreSQL с таймаутом из config/config.py
		return psycopg2.connect(
			dbname=self.dbname,
			user=self.user,
			password=self.password,
			host=self.host,
			port=self.port,
			connect_timeout=self.connect_timeout
		)

	def _save_to_database(self, symbol, buy_ex, sell_ex, buy_p, sell_p, spread_pct, volume_24h):
		# SQL-запрос для вставки найденной арбитражной связки в таблицу
		sql = """
			INSERT INTO possible_trades 
			(timestamp, symbol, buy_exchange, sell_exchange, buy_price, sell_price, spread_pct, volume_24h)
			VALUES (CURRENT_TIMESTAMP, %s, %s, %s, %s, %s, %s, %s);
		"""
		conn = None
		try:
			conn = self._get_connection()
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
			# Пишем ошибку и в лог-файл, и в консоль
			logger.error(f"🚨 [DB ERROR] Ошибка записи {symbol} в PostgreSQL: {e}")
			print(f"🚨 [DB ERROR]: Ошибка записи в PostgreSQL: {e}", flush=True)
		finally:
			# Гарантированно закрываем соединение с БД, даже если внутри try случилась ошибка
			if conn:
				conn.close()


	async def calculate_spot_spread(self, symbol: str, **kwargs) -> dict:
		"""
		Проходит по глубине стаканов двух бирж на объем base_order_usdt,
		считает средневзвешенную цену входа/выхода (VWAP), вычитает комиссии
		и отсекает неликвидные связки или аномалии.
		"""
		try:
			ex_a_name = kwargs.get("exchange_a_name")
			ex_b_name = kwargs.get("exchange_b_name")
			ob_a = kwargs.get("orderbook_a")
			ob_b = kwargs.get("orderbook_b")
			vol_24h = float(kwargs.get("volume_24h", 0.0))

			# Берем параметры из аргументов или из настроек класса (config/config.py)
			min_threshold = float(kwargs.get("min_spread_pct", self.min_spread_pct))
			max_threshold = float(kwargs.get("max_spread_pct", self.max_spread_pct))
			fee_pct = float(kwargs.get("trade_fee_pct", self.trade_fee_pct))
			order_usdt = float(kwargs.get("base_volume", self.base_order_usdt))

			if not ob_a or not ob_b or not ex_a_name or not ex_b_name or order_usdt <= 0:
				return {}

			asks_a = ob_a.get("asks", [])
			bids_a = ob_a.get("bids", [])
			asks_b = ob_b.get("asks", [])
			bids_b = ob_b.get("bids", [])

			if not asks_a or not bids_a or not asks_b or not bids_b:
				return {}

			def calc_real_direction(buy_asks: list, sell_bids: list, target_usdt: float) -> tuple:
				"""
				Симулирует покупку на target_usdt по стакану asks и продажу купленных монет в bids.
				Возвращает (avg_buy_price, avg_sell_price, net_spread_pct) или (0.0, 0.0, -999.0),
				если в стакане не хватает ликвидности.
				"""
				remaining_usdt = target_usdt
				total_coins_bought = 0.0

				# 1. Идем вглубь стакана продавцов (asks) на бирже покупки
				for level in buy_asks:
					if not isinstance(level, (list, tuple)) or len(level) < 2:
						continue
					price = float(level[0])
					amount_coins = float(level[1])
					if price <= 0 or amount_coins <= 0:
						continue

					level_usdt = price * amount_coins
					if level_usdt >= remaining_usdt:
						# На этом уровне закрываем остаток нашего ордера
						coins_here = remaining_usdt / price
						total_coins_bought += coins_here
						remaining_usdt = 0.0
						break
					else:
						# Выкупаем весь уровень целиком и идем глубже
						total_coins_bought += amount_coins
						remaining_usdt -= level_usdt

				# Если стакан закончился раньше, чем мы набрали монет на target_usdt — бракуем сделку!
				if remaining_usdt > 0.01 or total_coins_bought <= 0:
					return 0.0, 0.0, -999.0

				avg_buy_price = target_usdt / total_coins_bought

				# 2. Идем вглубь стакана покупателей (bids) на бирже продажи и сбываем все купленные монеты
				remaining_coins = total_coins_bought
				total_usdt_received = 0.0

				for level in sell_bids:
					if not isinstance(level, (list, tuple)) or len(level) < 2:
						continue
					price = float(level[0])
					amount_coins = float(level[1])
					if price <= 0 or amount_coins <= 0:
						continue

					if amount_coins >= remaining_coins:
						total_usdt_received += remaining_coins * price
						remaining_coins = 0.0
						break
					else:
						total_usdt_received += amount_coins * price
						remaining_coins -= amount_coins

				# Если на бирже продажи в стакане не хватило покупателей на весь наш объем — бракуем!
				if remaining_coins > 1e-8 or total_usdt_received <= 0:
					return 0.0, 0.0, -999.0

				avg_sell_price = total_usdt_received / total_coins_bought

				# Считаем реальный чистый спред с учетом проскальзывания и двойной комиссии
				raw_spread = ((avg_sell_price - avg_buy_price) / avg_buy_price) * 100.0
				net_spread = raw_spread - (fee_pct * 2.0)

				return avg_buy_price, avg_sell_price, net_spread

			# Просчитываем оба направления с погружением в глубину стаканов
			buy_p1, sell_p1, net_spread_1 = calc_real_direction(asks_a, bids_b, order_usdt)
			buy_p2, sell_p2, net_spread_2 = calc_real_direction(asks_b, bids_a, order_usdt)

			# БЛОК ОТЛАДКИ ГЛУБИНЫ СТАКАНОВ (раскомментировать при необходимости)
			# print(f"DEBUG VWAP [{symbol}] {ex_a_name}<->{ex_b_name} на ${order_usdt}: net_1={net_spread_1:.3f}%, net_2={net_spread_2:.3f}%")

			final_res = {}

			# Выбираем лучшее направление и проверяем попадание в коридор [min_threshold; max_threshold]
			if net_spread_1 >= net_spread_2:
				if min_threshold <= net_spread_1 <= max_threshold:
					final_res = {
						"symbol": symbol.upper(),
						"buy_exchange": str(ex_a_name).upper(),
						"sell_exchange": str(ex_b_name).upper(),
						"buy_price": round(buy_p1, 8),
						"sell_price": round(sell_p1, 8),
						"spread_pct": round(net_spread_1, 3),
						"volume_24h": vol_24h
					}
			else:
				if min_threshold <= net_spread_2 <= max_threshold:
					final_res = {
						"symbol": symbol.upper(),
						"buy_exchange": str(ex_b_name).upper(),
						"sell_exchange": str(ex_a_name).upper(),
						"buy_price": round(buy_p2, 8),
						"sell_price": round(sell_p2, 8),
						"spread_pct": round(net_spread_2, 3),
						"volume_24h": vol_24h
					}

			if final_res:
				self.db.save_possible_trade(
					symbol=final_res["symbol"],
					buy_ex=final_res["buy_exchange"],
					sell_ex=final_res["sell_exchange"],
					buy_p=final_res["buy_price"],
					sell_p=final_res["sell_price"],
					spread_pct=final_res["spread_pct"],
					volume_24h=final_res["volume_24h"]
				)
				return final_res


		except Exception as e:
			logger.error(f"🚨 [ANALYZER ERROR] Критическая ошибка расчета {symbol}: {e}")
			print(f"🚨 [ANALYZER ERROR]: Критическая ошибка расчета {symbol}: {e}", flush=True)

		return {}

