# Модуль: exchanges/bybit.py
import os
import ccxt.pro as ccxt_lib  # Используем асинхронный CCXT
from typing import Dict
from exchanges.base import BaseExchange
from config import settings

class BybitExchange(BaseExchange):
	"""
	Класс-реализация для работы с биржей Bybit через библиотеку CCXT.
	Полностью изолирует спотовый рынок и настраивает Демо-аккаунт ЕТА.
	"""

	def __init__(self):
		super().__init__(exchange_id='bybit')
		self.private_api = None  # Изолированный клиент для баланса

	async def init_exchange(self):
		"""Инициализирует подключение к Bybit, разделяя публичный и демо-режимы"""
		await super().init_exchange()
		
		if self.api:
			self.api.options['adjustForTimeDifference'] = True
			# --- КРИТИЧЕСКАЯ ЗАЩИТА ОТ ЛИШНИХ ЗАПРОСОВ CCXT ---
			# Удаляем типы контрактов, которые вызывают ошибки instruments-info по ETH и опционам
			if 'implementedMarkets' in self.api.options:
				self.api.options['implementedMarkets'] = {'spot': True}
			else:
				self.api.options['implementedMarkets'] = {'spot': True}
				
			print("📈 [BYBIT] Публичный коннектор цен успешно инициализирован.")

		# Парсим .env для настройки приватного демо-клиента кошелька
		env_path = os.path.join(os.getcwd(), '.env')
		api_key = None
		secret_key = None
		
		if os.path.exists(env_path):
			with open(env_path, 'r', encoding='utf-8') as f:
				for line in f:
					if '=' in line and not line.startswith('#'):
						key, value = line.strip().split('=', 1)
						value = value.strip().strip('"').strip("'")
						if key == 'BYBIT_API_KEY':
							api_key = value
						elif key == 'BYBIT_SECRET_KEY':
							secret_key = value

		if api_key and secret_key:
			# Создаем отдельный экземпляр CCXT специально под Единый Демо-аккаунт Bybit V5
			self.private_api = ccxt_lib.bybit({
				'apiKey': api_key,
				'secret': secret_key,
				'enableRateLimit': True,
				'options': {
					'adjustForTimeDifference': True,
					'defaultType': 'unified'  # Указываем Единый Торговый Аккаунт для Демо-режима
				}
			})
			# Для Mainnet Demo используется стандартный адрес, но CCXT сам подставит нужные заголовки демо-торговли
			self.private_api.urls['api']['private'] = 'https://api.bybit.com'
			self.bybit_has_keys = True
			print("🔐 [BYBIT] Приватный коннектор кошелька подключен (Режим: Демо-аккаунт).")
		else:
			self.bybit_has_keys = False
			print("⚠️ [BYBIT] API-ключи в .env не найдены. Будет доступен только сбор цен.")

	async def fetch_balance_usdt(self) -> float:
		"""Запрашивает баланс Единого торгового аккаунта демо-профиля"""
		if not getattr(self, 'bybit_has_keys', False) or self.private_api is None:
			return 0.0
		try:
			balance_data = await self.private_api.fetch_balance()
			# В Едином аккаунте Bybit баланс лежит в общей структуре total -> USDT
			usdt_balance = balance_data.get('total', {}).get('USDT', 0.0)
			return float(usdt_balance)
		except Exception as e:
			# Если ключи демо-аккаунта еще не активировались на стороне биржи, возвращаем 0
			return 0.0


	async def fetch_order_book(self, symbol: str, limit: int = 5) -> Optional[dict]:
		"""
		Переопределенный метод получения стакана Bybit.
		Жестко заставляет биржу отдавать ТОЛЬКО спотовый стакан, полностью убирая ошибки category=option.
		"""
		if not self.api:
			return None
		try:
			# Передаем params={'category': 'spot'} — это полностью отключит запросы к опционам!
			return await self.api.fetch_order_book(symbol, limit=limit, params={'category': 'spot'})
		except Exception as e:
			# Ничего не принтуем в консоль, чтобы не флудить
			return None


	async def fetch_tickers(self) -> Dict[str, Dict[str, float]]:
		if not self.api:
			return {}
		try:
			# Передаем params={'category': 'spot'}, чтобы Bybit ВООБЩЕ не лез в опционы!
			raw_tickers = await self.api.fetch_tickers(params={'category': 'spot'})

			normalized_tickers = {}
			total_processed = 0
			filtered_by_volume = 0
			
			for symbol, data in raw_tickers.items():
				if not symbol.endswith("/USDT"):
					continue
				
				total_processed += 1
				price = data.get('last')
				volume_base = data.get('baseVolume')
				
				if price is not None and volume_base is not None:
					volume_usdt = float(volume_base) * float(price)
					
					if volume_usdt < settings.MIN_24H_VOLUME_USDT:
						filtered_by_volume += 1
						continue
					
					display_symbol = f"{symbol} (Bybit)"
					normalized_tickers[display_symbol] = {
						'price': float(price),
						'volume': float(volume_base)
					}
			
			if total_processed > 0:
				#print(f"🧹 [ФИЛЬТР] Из {total_processed} спотовых пар отсеяно {filtered_by_volume} низколиквидных монет (меньше ${settings.MIN_24H_VOLUME_USDT:,})")
			
				return normalized_tickers

		except Exception as e:
			print(f"⚠️ [BYBIT] Ошибка сбора данных через CCXT: {e}")
			return {}

	async def close(self):
		"""Закрытие сессий обоих коннекторов при остановке"""
		await super().close()
		if self.private_api:
			await self.private_api.close()
