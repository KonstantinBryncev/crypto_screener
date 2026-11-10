# Модуль: notifications/console.py
from datetime import datetime

class ConsoleNotifier:
    """Модуль прямого вывода сигналов скринера в консоль разработчика"""

    def print_signals(self, signals: list):
        """Форматирует и мгновенно выводит список обнаруженных аномалий через print"""
        current_time = datetime.now().strftime("%H:%M:%S")
        for signal in signals:
            alert_msg = (
                f"🔥 {current_time} [СИГНАЛ] {signal['direction']} | "
                f"Пара: {signal['symbol']} | "
                f"Спред: {signal['delta']}% | "
                f"{signal['main_metric']} | "
                f"{signal['volume_info']}"
            )
            # Форсим прямой вывод в консоль ConEmu в обход логера
            print(alert_msg, flush=True)


