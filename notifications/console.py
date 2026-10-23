# Модуль: notifications/console.py
import logging
from datetime import datetime

# Настраиваем базовый формат логирования: Время -> Сообщение
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)

class ConsoleNotifier:
    """Модуль вывода сигналов скринера в консоль разработчика"""

    def print_signals(self, signals: list):
        """Красиво форматирует и выводит список обнаруженных аномалий"""
        for signal in signals:
            alert_msg = (
                f"{signal['direction']} | "
                f"Пара: {signal['symbol']} | "
                f"Изм: {signal['delta']}% | "
                f"{signal['main_metric']} | "
                f"{signal['volume_info']}"
            )
            logging.warning(alert_msg)


