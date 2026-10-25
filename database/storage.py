import os
import csv
from datetime import datetime
import logging
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger("ScreenerStorage")

class SignalStorage:
	"""
	Компонент для надежной асинхронной и потоковой записи 
	арбитражных окон и технических сигналов аномалий на жесткий диск.
	"""
	
	def __init__(self, arbitrage_csv_path: Path, signals_csv_path: Path):
		"""
		Инициализация файлового хранилища данных.
		Пути вычисляются на основе config_bot.json и передаются сюда диспетчером.
		"""
		self.arbitrage_file = arbitrage_csv_path
		self.signals_file = signals_csv_path
		
		# Автоматически создаем родительские папки для файлов, если их физически не существовало
		self.arbitrage_file.parent.mkdir(parents=True, exist_ok=True)
		self.signals_file.parent.mkdir(parents=True, exist_ok=True)
		
		# Запуск процедуры проверки и генерации заголовков таблиц
		self._init_files()

	def _init_files(self):
		"""Создает CSV файлы со структурами заголовков, если они не существуют."""
		if not self.arbitrage_file.exists():
			with open(self.arbitrage_file, mode="w", newline="", encoding="utf-8") as f:
				writer = csv.writer(f, delimiter=";")
				writer.writerow([
					"Timestamp", 
					"Symbol", 
					"Buy_Exchange", 
					"Sell_Exchange", 
					"Buy_Price", 
					"Sell_Price", 
					"Raw_Spread_Pct", 
					"Net_Profit_USDT"
				])
				
		if not self.signals_file.exists():
			with open(self.signals_file, mode="w", newline="", encoding="utf-8") as f:
				writer = csv.writer(f, delimiter=";")
				writer.writerow([
					"Timestamp", 
					"Exchange", 
					"Symbol", 
					"Type", 
					"Price", 
					"Metric_Value", 
					"Description"
				])

	def save_arbitrage(self, data: Dict[str, Any]):
		"""Записывает строку с параметрами обнаруженного прибыльного межбиржевого окна."""
		try:
			with open(self.arbitrage_file, mode="a", newline="", encoding="utf-8") as f:
				writer = csv.writer(f, delimiter=";")
				writer.writerow([
					datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
					data.get("symbol"),
					data.get("buy_exchange"),
					data.get("sell_exchange"),
					data.get("buy_price"),
					data.get("sell_price"),
					data.get("raw_spread_pct"),
					data.get("net_profit_usdt")
				])
		except Exception as e:
			logger.error(f"Не удалось сохранить арбитраж в базу CSV: {e}")

	def save_signal(self, data: Dict[str, Any]):
		"""Записывает строку с параметрами технического торгового сигнала (памп/дамп/объемы)."""
		try:
			with open(self.signals_file, mode="a", newline="", encoding="utf-8") as f:
				writer = csv.writer(f, delimiter=";")
				writer.writerow([
					datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
					data.get("exchange"),
					data.get("symbol"),
					data.get("type"),
					data.get("price"),
					data.get("metric_value"),
					data.get("description")
				])
		except Exception as e:
			logger.error(f"Не удалось сохранить технический сигнал в базу CSV: {e}")
