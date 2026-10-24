# run_signals.py
import asyncio
import sys
import logging
import warnings

logging.getLogger("ccxt").setLevel(logging.CRITICAL)
logging.getLogger("asyncio").setLevel(logging.CRITICAL)
logging.getLogger("urllib3").setLevel(logging.CRITICAL)
warnings.filterwarnings("ignore")

from core.signal_manager.py import SignalManager

async def main():
	print("==================================================")
	print("        ЗАПУСК: СКРИНЕР СИГНАЛОВ И ПАМПОВ         ")
	print("==================================================")
	
	manager = SignalManager()
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
