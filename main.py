# main.py
import asyncio
import sys
import logging
import warnings

# НАМЕРТВО ГЛУШИМ СИСТЕМНЫЙ ФЛУД БИБЛИОТЕК В КОНСОЛИ
logging.getLogger("ccxt").setLevel(logging.CRITICAL)
logging.getLogger("asyncio").setLevel(logging.CRITICAL)
logging.getLogger("urllib3").setLevel(logging.CRITICAL)

# Отключаем предупреждения самого Python (например, о депрекации селекторов окон)
warnings.filterwarnings("ignore")

from core.manager import TickerManager

async def main():
	print("==================================================")
	print("   ЗАПУСК АСИНХРОННОГО КРИПТО-СКРИНЕРА И АРБИТРАЖА")
	print("==================================================")
	
	manager = TickerManager()
	
	try:
		await manager.start()
	except KeyboardInterrupt:
		print("\n[MAIN] Получен сигнал от пользователя. Завершение работы...")
	except Exception as e:
		print(f"\n❌ [КРИТИЧЕСКАЯ ОШИБКА ИСПОЛНЕНИЯ БОТА]: {e}")
		import traceback
		traceback.print_exc()
	finally:
		await manager.stop()
		print("==================================================")
		print("          РАБОТА БОТА УСПЕШНО ЗАВЕРШЕНА")
		print("==================================================")

if __name__ == "__main__":
	if sys.platform == 'win32':
		asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
		
	try:
		asyncio.run(main())
	except KeyboardInterrupt:
		pass
