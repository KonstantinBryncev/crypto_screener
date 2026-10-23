# Модуль: database/storage.py
import csv
import os
from datetime import datetime
import asyncio
from config import settings

class CSVSignalStorage:
	"""
	Модуль для асинхронного сохранения сигналов и истории баланса в CSV.
	Использует потокобезопасную очередь для исключения разрывов строк.
	"""

	def __init__(self):
		self.file_path = settings.SIGNALS_CSV_FILE
		self.balance_file_path = self.file_path.parent / "balance_history.csv"
		
		self.headers = ["Timestamp", "Type", "Symbol", "Direction", "Delta_Pct", "Main_Metric", "Volume_Info"]
		self.balance_headers = ["Timestamp", "Balance_USDT"]
		
		self.queue = asyncio.Queue()
		
		self._init_csv_files()
		asyncio.create_task(self._queue_worker())

	def _init_csv_files(self):
		"""Создание файлов и запись заголовков"""
		self.file_path.parent.mkdir(parents=True, exist_ok=True)
		
		# Инициализация файла сигналов
		if not self.file_path.exists():
			with open(self.file_path, mode="w", newline="", encoding="utf-8-sig") as f:
				writer = csv.writer(f, delimiter=";")
				writer.writerow(self.headers)
				
		# Инициализация файла баланса
		if not self.balance_file_path.exists():
			with open(self.balance_file_path, mode="w", newline="", encoding="utf-8-sig") as f:
				writer = csv.writer(f, delimiter=";")
				writer.writerow(self.balance_headers)
			print(f"📁 [БАЗА ДАННЫХ] Создан новый файл истории баланса: {self.balance_file_path.name}")

	def _write_row_sync(self, task_type: str, data: dict):
		"""Синхронная физическая запись на диск в зависимости от типа задачи"""
		current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
		
		if task_type == "SIGNAL":
			with open(self.file_path, mode="a", newline="", encoding="utf-8-sig") as f:
				writer = csv.writer(f, delimiter=";")
				writer.writerow([
					current_time,
					data.get("type", "UNKNOWN"),
					data.get("symbol", "UNKNOWN"),
					data.get("direction", "UNKNOWN"),
					data.get("delta", 0.0),
					data.get("main_metric", ""),
					data.get("volume_info", "")
				])
		elif task_type == "BALANCE":
			with open(self.balance_file_path, mode="a", newline="", encoding="utf-8-sig") as f:
				writer = csv.writer(f, delimiter=";")
				writer.writerow([current_time, data.get("balance", 0.0)])

	async def _queue_worker(self):
		"""Разборщик очереди задач"""
		while True:
			task_type, data = await self.queue.get()
			try:
				await asyncio.to_thread(self._write_row_sync, task_type, data)
			except Exception as e:
				print(f"❌ [БАЗА ДАННЫХ] Ошибка фоновой записи: {e}")
			finally:
				self.queue.task_done()

	def add_to_save_queue(self, signal: dict):
		"""Добавление сигнала в очередь"""
		self.queue.put_nowait(("SIGNAL", signal))

	def add_balance_to_queue(self, balance_val: float):
		"""Добавление значения баланса в очередь записи"""
		self.queue.put_nowait(("BALANCE", {"balance": balance_val}))
