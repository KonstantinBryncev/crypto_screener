# Модуль: exchanges/bybit.py
from typing import Dict
from exchanges.base import BaseExchange
from config import settings

class BybitExchange(BaseExchange):
	"""
	Класс-реализация для работы с биржей Bybit.
	Наследуется от базового класса BaseExchange.
	"""

	def __init__(self):
		# Вызываем конструктор базового класса и передаем id 'bybit' для CCXT
		super().__init__(exchange_id='bybit')

	async def init_exchange(self):
		"""
		Инициализирует подключение к Bybit в публичном режиме.
		Для работы скринера (сбора цен и объемов) API-ключи и демо-режим не нужны.
		"""
		# Вызываем базовую настройку (она создаст объект api и настроит прокси, если они есть)
		await super().init_exchange()
		
		if self.api:
			# Мы НЕ передаем ключи и НЕ включаем sandbox_mode.
			# Это заставит ccxt делать обычные публичные REST-запросы к основному рынку.
			print("📈 [BYBIT] Успешно подключен к основному рынку в публичном режиме (без ключей).")

	async def fetch_tickers(self) -> Dict[str, Dict[str, float]]:
		"""
		Собирает текущие цены и объемы.
		Фильтрует мусорные монеты с низким суточным объемом торгов.
		"""
		if self.api is None:
			raise RuntimeError("Биржа не инициализирована! Сначала вызовите init_exchange()")

		try:
			# Асинхронно запрашиваем тикеры
			raw_tickers = await self.api.fetch_tickers()
			normalized_tickers = {}
			
			# Счётчики для красивого лога в консоли
			total_processed = 0
			filtered_by_volume = 0
			
			for symbol, data in raw_tickers.items():
				if not symbol.endswith("/USDT"):
					continue
				
				total_processed += 1
				
				price = data.get('last')
				volume_base = data.get('baseVolume') # Объем в самой монете (например, в BTC)
				
				if price is not None and volume_base is not None:
					# Рассчитываем суточный объем торгов в USDT (в долларах)
					volume_usdt = float(volume_base) * float(price)
					
					# ГЛАВНЫЙ ФИЛЬТР: Если объем меньше заданного в settings, пропускаем монету
					if volume_usdt < settings.MIN_24H_VOLUME_USDT:
						filtered_by_volume += 1
						continue
					
					# Маркируем как Bybit
					display_symbol = f"{symbol} (Bybit)"
					
					normalized_tickers[display_symbol] = {
						'price': float(price),
						'volume': float(volume_base) # Для истории объемов оставляем базовый объем
					}
			
			# Раз в цикл выводим в консоль легкий отчет о чистке мусора
			if total_processed > 0:
				print(f"🧹 [ФИЛЬТР] Из {total_processed} пар отсеяно {filtered_by_volume} низколиквидных монет (меньше ${settings.MIN_24H_VOLUME_USDT:,})")
			
			return normalized_tickers

		except Exception as e:
			print(f"⚠️ [BYBIT] Ошибка при получении тикеров: {e}")
			return {}

