# main.py
import asyncio
import sys
from core.manager import TickerManager
import logging
# Глушим системные варнинги библиотек (ccxt, asyncio, urllib3), оставляя только важные ошибки
logging.getLogger("ccxt").setLevel(logging.ERROR)
logging.getLogger("asyncio").setLevel(logging.ERROR)
# Если у вас настроен корневой логгер, можно принудительно выставить уровень:
logging.basicConfig(level=logging.ERROR, format='%(asctime)s [%(levelname)s] %(message)s')


async def main():
	print("==================================================")
	print("   ЗАПУСК АСИНХРОННОГО КРИПТО-СКРИНЕРА И АРБИТРАЖА")
	print("==================================================")
	
	# Инициализируем наш главный объединенный диспетчер
	manager = TickerManager()
	
	try:
		# Запускаем основной цикл (опрос тикеров + фоновый баланс + фоновый арбитраж)
		await manager.start()
	except KeyboardInterrupt:
		print("\n[MAIN] Получен сигнал от пользователя. Завершение работы...")
	except Exception as e:
		print(f"\n❌ [КРИТИЧЕСКАЯ ОШИБКА ПРИ РАБОТЕ]: {e}")
	finally:
		# На всякий случай гарантируем закрытие сессий
		await manager.stop()
		print("==================================================")
		print("          РАБОТА БОТА УСПЕШНО ЗАВЕРШЕНА")
		print("==================================================")

	if __name__ == "__main__":
		# Оптимизация работы asyncio под Windows 10 для старых процессоров
		if sys.platform == 'win32':
			asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
			
		try:
			asyncio.run(main())
		except KeyboardInterrupt:
			pass
