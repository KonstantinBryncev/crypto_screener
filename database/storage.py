# Модуль: database/storage.py
import csv
import os
from datetime import datetime
import asyncio
from config import settings

class CSVSignalStorage:
    """
    Модуль для асинхронного сохранения сигналов скринера в локальный CSV-файл.
    Использует потокобезопасную очередь asyncio.Queue, что полностью исключает
    смешивание и разрыв строк при массовых сигналах.
    """

    def __init__(self):
        self.file_path = settings.SIGNALS_CSV_FILE
        self.headers = ["Timestamp", "Type", "Symbol", "Direction", "Delta_Pct", "Main_Metric", "Volume_Info"]
        
        # Создаем асинхронную очередь для сигналов
        self.queue = asyncio.Queue()
        
        # Сразу инициализируем файл
        self._init_csv_file()
        
        # Запускаем фоновый вечный таск, который будет разбирать очередь
        asyncio.create_task(self._queue_worker())

    def _init_csv_file(self):
        """Синхронный метод создания файла и записи заголовков"""
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.file_path.exists():
            with open(self.file_path, mode="w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f, delimiter=";")
                writer.writerow(self.headers)
            print(f"📁 [БАЗА ДАННЫХ] Создан новый файл истории: {self.file_path.name}")

    def _write_row_sync(self, signal: dict):
        """Синхронная физическая запись одной строки на жесткий диск"""
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(self.file_path, mode="a", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow([
                current_time,
                signal.get("type", "UNKNOWN"),
                signal.get("symbol", "UNKNOWN"),
                signal.get("direction", "UNKNOWN"),
                signal.get("delta", 0.0),
                signal.get("main_metric", ""),
                signal.get("volume_info", "")
            ])

    async def _queue_worker(self):
        """Фоновый рабочий, который по очереди забирает сигналы из коробки и пишет на диск"""
        while True:
            # Ждем, пока в очереди появится хотя бы один сигнал (код спит и не тратит CPU)
            signal = await self.queue.get()
            
            try:
                # Безопасно пишем строку в фоновом потоке Windows
                await asyncio.to_thread(self._write_row_sync, signal)
            except Exception as e:
                print(f"❌ [БАЗА ДАННЫХ] Ошибка фоновой записи: {e}")
            finally:
                # Сообщаем очереди, что задача успешно обработана
                self.queue.task_done()

    def add_to_save_queue(self, signal: dict):
        """
        Публичный метод для мгновенного добавления сигнала в очередь.
        Работает мгновенно, не блокируя ядро скринера.
        """
        self.queue.put_nowait(signal)
