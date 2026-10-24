# run_arbitrage.py
import asyncio
import sys
import logging
import warnings

logging.getLogger("ccxt").setLevel(logging.CRITICAL)
logging.getLogger("asyncio").setLevel(logging.CRITICAL)
logging.getLogger("urllib3").setLevel(logging.CRITICAL)
warnings.filterwarnings("ignore")

from core.arbitrage_manager import ArbitrageManager

async def main():
	print("==================================================")
	print("        ЗАПУСК: МЕЖБИРЖЕВОЙ АРБИТРАЖНЫЙ СКРИНЕР   ")
	print("==================================================")
	
	manager = ArbitrageManager()
	try:
		await manager.start()
	except KeyboardInterrupt:
		print("\n[MAIN] Завершение работы пользователем...")
	finally:
		await manager.stop()
		print("==================================================")

if __name__ == "__main__":
	if sys.platform == 'win32':
		asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
	try:
		asyncio.run(main())
	except KeyboardInterrupt:
		pass
