# Модуль: main.py
import asyncio
import warnings
from core.manager import TickerManager

# Полностью отключаем вывод предупреждений (Deprecation и Runtime), 
# чтобы сетевой шум от CCXT не засорял нашу консоль
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)
warnings.filterwarnings("ignore", message=".*bybit GET.*")

async def main():
    # Создаем экземпляр главного менеджера скринера
    manager = TickerManager()
    
    try:
        # Запускаем бесконечный асинхронный цикл сбора данных
        await manager.start()
    except KeyboardInterrupt:
        # Перехватываем стандартное закрытие через Ctrl+C в консоли Windows
        print("\n[СИСТЕМА] Получен сигнал от пользователя. Завершение работы...")
    finally:
        # Гарантируем, что сетевые сокеты закроются, даже если бот упадет с ошибкой
        await manager.stop()

if __name__ == "__main__":
    # В Python 3.15+ asyncio.run() сам настраивает циклы событий на Windows
    asyncio.run(main())
