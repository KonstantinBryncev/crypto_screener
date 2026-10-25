# run_arbitrage.py
import asyncio
import sys
import logging
import warnings

# ОТКЛЮЧЕНИЕ ШУМА В ЛОГАХ
logging.getLogger("asyncio").setLevel(logging.CRITICAL)
logging.getLogger("urllib3").setLevel(logging.CRITICAL)
warnings.filterwarnings("ignore")

try:
	from core.arbitrage_manager import ArbitrageManager
except ModuleNotFoundError:
	from arbitrage_manager import ArbitrageManager

async def main():
	"""
	Главная асинхронная точка входа в скринер межбиржевого арбитража.
	"""
	# Используем принудительный сброс буфера (flush=True), чтобы Windows выводила текст мгновенно
	print("==================================================", flush=True)
	print("        ЗАПУСК: МЕЖБИРЖЕВОЙ АРБИТРАЖНЫЙ СКРИНЕР   ", flush=True)
	print("==================================================", flush=True)
	
	print("🔍 [ШАГ 1] Инициализация класса ArbitrageManager...", flush=True)
	manager = ArbitrageManager()
	
	print("🔍 [ШАГ 2] Запуск асинхронного старта скринера...", flush=True)
	try:
		await manager.start()
	except KeyboardInterrupt:
		print("\n[MAIN] Завершение работы пользователем...", flush=True)
	finally:
		await manager.stop()
		print("==================================================", flush=True)

if __name__ == "__main__":
	# УБРАНО: io.TextIOWrapper, который вызывал блокировку буфера в .venv Windows
	if sys.platform == 'win32':
		asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
		
	try:
		asyncio.run(main())
	except KeyboardInterrupt:
		pass
