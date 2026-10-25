class ArbitrageAnalyzer:
	def __init__(self):
		"""
		Очищенный анализатор стаканов. 
		Все настройки и проценты комиссий перенесены в config_bot.json.
		"""
		pass

	def calculate_spot_spread(self, symbol: str, exchange_a_name: str, orderbook_a: dict, exchange_b_name: str, orderbook_b: dict, transfer_fee: float = 1.0, base_volume: float = 1000.0, min_spread_pct: float = -10, trade_fee_pct: float = 0.002):
		"""
		Рассчитывает чистый спред и выводит сигнал на основе параметров из config_bot.json.
		"""
		# Проверяем, что стаканы содержат списки котировок
		if not orderbook_a.get('asks') or not orderbook_b.get('bids'):
			return None

		try:
			# Извлекаем цены: строго первый (лучший) ордер из числового массива
			buy_price = orderbook_a['asks'][0][0]
			sell_price = orderbook_b['bids'][0][0]
		except (IndexError, TypeError):
			return None

		if buy_price <= 0 or sell_price <= 0:
			return None

		# 1. Считаем грязный спред в процентах
		raw_spread_pct = ((sell_price - buy_price) / buy_price) * 100

		# 2. Вычитаем издержки: торговую комиссию (trade_fee_pct) и сетевой перевод из конфига
		transfer_fee_pct = (transfer_fee / base_volume) * 100
		net_spread_pct = raw_spread_pct - (trade_fee_pct * 100) - transfer_fee_pct

		# 3. ФИЛЬТРАЦИЯ ПО КОНФИГУ: Слушаемся динамического min_spread_pct
		if net_spread_pct < min_spread_pct:
			print(min_spread_pct)
			return None

		# Рассчитываем чистую прибыль в USDT от объема базового ордера
		expected_profit = (base_volume * (net_spread_pct / 100))
		display_symbol = symbol.upper().replace('_', '/')

		# Если чистый спред вышел в плюс — помечаем как сигнал, если в минус — как мониторинг
		status_marker = "🚨 [АРБИТРАЖНЫЙ СИГНАЛ]" if net_spread_pct > 0 else "📊 [МОНИТОРИНГ СПРЕДА]"

		# 4. ВЫВОД РЕЗУЛЬТАТА В КОНСОЛЬ
		print(f"{status_marker} [{display_symbol}]")
		print(f"   Купить на {exchange_a_name.upper()} по {buy_price}")
		print(f"   Продать на {exchange_b_name.upper()} по {sell_price}")
		print(f"   Чистый спред: {net_spread_pct:.2f}% | Ожидаемый профит: {expected_profit:.4f} USDT")
		print("-" * 50)

		return {
			'symbol': display_symbol,
			'buy_exchange': exchange_a_name,
			'buy_price': buy_price,
			'sell_exchange': exchange_b_name,
			'sell_price': sell_price,
			'net_spread_pct': round(net_spread_pct, 2),
			'net_profit': round(expected_profit, 4)
		}
