import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("ArbitrageAnalyzer")

class ArbitrageAnalyzer:
	"""
	Математическое ядро криптоскринера.
	Проводит расчет межбиржевых спредов и чистой прибыли.
	"""
	
	def __init__(self):
		pass

	def calculate_spot_spread(
		self, 
		symbol: str, 
		exchange_a_name: str, 
		orderbook_a: Dict[str, Any], 
		exchange_b_name: str, 
		orderbook_b: Dict[str, Any],
		transfer_fee: float, # Больше не используется как единая константа
		base_volume: float,
		min_spread_pct: float,
		trade_fee_pct: float
	) -> Optional[Dict[str, Any]]:
		
		bids_a, asks_a = orderbook_a.get('bids', []), orderbook_a.get('asks', [])
		bids_b, asks_b = orderbook_b.get('bids', []), orderbook_b.get('asks', [])

		if not bids_a or not asks_a or not bids_b or not asks_b:
			return None

		buy_price = float(asks_a[0][0])  
		sell_price = float(bids_b[0][0]) 

		if sell_price <= buy_price:
			return None

		raw_spread = ((sell_price - buy_price) / buy_price) * 100
		if raw_spread < min_spread_pct:
			return None

		# =========================================================================
		# ХАРДКОД РЕАЛЬНЫХ СЕТЕВЫХ КОМИССИЙ НА ВЫВОД (WITHDRAWAL FEES) ДЛЯ ТОП-МОНЕТ
		# =========================================================================
		asset = symbol.split('/')[0].upper()
		
		# Задаем среднюю комиссию в самих монетах (копирует реальные тарифы бирж)
		network_fees_in_crypto = {
			"ADA": 1.0,      # ~ 0.4-0.8 USDT
		    "ALGO": 0.1,     # ~ единичные центы
		    "ATOM": 0.01,    # ~ 0.1 USDT
		    "XLM": 0.02,     # ~ меньше цента
		    "EOS": 0.1,      # ~ меньше цента
		    "APT": 0.01,     # ~ 0.1 USDT
		    "SUI": 0.1,      # ~ 0.2 USDT
		    "NEAR": 0.05,    # ~ 0.2 USDT
		    "FTM": 0.5,      # ~ 0.3 USDT
		    "INJ": 0.05,     # ~ 0.8 USDT
		    "BONK": 20000.0, # ~ 0.5 USDT (в сети SOL)
		    "WIF": 0.2,       # ~ 0.5 USDT (в сети SOL)
			"BTC": 0.0005,
			"ETH": 0.003,
			"LTC": 0.001,
			"XRP": 0.2,
			"SOL": 0.01,
			"DOGE": 2.0,
			"DOT": 0.1,
			"LINK": 0.5,
			"AVAX": 0.01,
			"TRX": 10.0
		}
		
		# Извлекаем комиссию для монеты, если ее нет — берем дефолт из конфига (в USDT)
		if asset in network_fees_in_crypto:
			crypto_fee = network_fees_in_crypto[asset]
		else:
			crypto_fee = transfer_fee / buy_price # Дефолтный костыль

		# =========================================================================
		# ЭТАЛОННАЯ СПОТОВАЯ ЦЕПОЧКА ТОРГОВЛИ И КОМИССИЙ
		# =========================================================================
		initial_usdt = base_volume
		
		# 1. Покупка на Бирже А
		buy_fee_usdt = initial_usdt * (trade_fee_pct / 100)
		clean_buy_usdt = initial_usdt - buy_fee_usdt
		crypto_amount = clean_buy_usdt / buy_price
		
		# 2. Трансфер (теперь вычитаем честную комиссию сети в крипте)
		crypto_after_transfer = crypto_amount - crypto_fee
		
		if crypto_after_transfer <= 0:
			return None

		# 3. Продажа на Бирже Б
		gross_sell_usdt = crypto_after_transfer * sell_price
		sell_fee_usdt = gross_sell_usdt * (trade_fee_pct / 100)
		final_usdt = gross_sell_usdt - sell_fee_usdt

		# Расчет чистого финансового профита
		net_profit_usdt = final_usdt - initial_usdt
		net_spread_pct = (net_profit_usdt / initial_usdt) * 100

		# Фильтруем: чистый профит должен быть строго больше нуля
		if net_profit_usdt <= 0:
			return None

		result = {
			"symbol": symbol,
			"buy_exchange": exchange_a_name.upper(),
			"sell_exchange": exchange_b_name.upper(),
			"buy_price": buy_price,
			"sell_price": sell_price,
			"raw_spread_pct": round(raw_spread, 2),
			"net_profit_usdt": round(net_profit_usdt, 2),
			"net_spread_pct": round(net_spread_pct, 2)
		}

		print(
			f"🔔 [СВЯЗКА НАЙДЕНА] {symbol} | "
			f"Купить: {result['buy_exchange']} ({buy_price:.4f}) ➡️ "
			f"Продать: {result['sell_exchange']} ({sell_price:.4f}) | "
			f"Чистый профит: {result['net_profit_usdt']:.2f} USDT ({result['net_spread_pct']:.2f}%)",
			flush=True
		)

		return result


	def analyze_market_signals(self, exchange_id: str, symbol: str, candles: List[List[float]], signals_config: Dict[str, Any]) -> List[Dict[str, Any]]:
		detected_signals = []
		lookback = int(signals_config["lookback_period"])
		price_threshold = float(signals_config["price_change_threshold"])
		vol_multiplier = float(signals_config["volume_multiplier"])
		volatility_multiplier = float(signals_config["volatility_multiplier"])

		if len(candles) < lookback + 1:
			return detected_signals

		historical = candles[:-1][-lookback:]
		current = candles[-1]
		
		c_open, c_high, c_low, c_close, c_volume = current[1], current[2], current[3], current[4], current[5]

		price_change_pct = ((c_close - c_open) / c_open) * 100

		if abs(price_change_pct) >= price_threshold:
			detected_signals.append({
				"exchange": exchange_id.upper(),
				"symbol": symbol,
				"type": "PUMP" if price_change_pct > 0 else "DUMP",
				"price": c_close,
				"metric": round(price_change_pct, 2),
				"msg": f"Аномальное движение цены: {price_change_pct:.2f}%"
			})

		avg_volume = sum(candle[5] for candle in historical) / len(historical)

		if avg_volume > 0:
			volume_ratio = c_volume / avg_volume
			if volume_ratio >= vol_multiplier:
				detected_signals.append({
					"exchange": exchange_id.upper(),
					"symbol": symbol,
					"type": "VOLUME_SPIKE",
					"price": c_close,
					"metric": round(volume_ratio, 2),
					"msg": f"Объем торгов превысил средний исторический в {volume_ratio:.2f} раз(а)"
				})

		avg_hist_range = sum(candle[2] - candle[3] for candle in historical) / len(historical)
		current_range = c_high - c_low

		if avg_hist_range > 0:
			volatility_ratio = current_range / avg_hist_range
			if volatility_ratio >= volatility_multiplier:
				detected_signals.append({
					"exchange": exchange_id.upper(),
					"symbol": symbol,
					"type": "HIGH_VOLATILITY",
					"price": c_close,
					"metric": round(volatility_ratio, 2),
					"msg": f"Ценовой диапазон свечи (High-Low) расширился в {volatility_ratio:.2f} раз(а)"
				})

		return detected_signals
