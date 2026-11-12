# Файл: main.py
import asyncio
import logging
import json

from config.config import CONFIG
from core.arbitrage_manager import ArbitrageManager
from database.db_manager import DatabaseManager

async def main():
					#>>>>>>LET'S DEBUG<<<<<<<
	#print(f"ПОЛНЫЙ ФАЙЛ КОНФИГ:\n{json.dumps(CONFIG, indent='\t', ensure_ascii=False)}\n{'='*60}\n")

	logging.basicConfig(
		level=logging.WARNING,
		filename='bot_errors.log',
		filemode='a',
		format='%(asctime)s - %(levelname)s - %(message)s',
		encoding='utf-8')

	DatabaseManager(CONFIG).init_tables()
	manager = ArbitrageManager(CONFIG)
	
	try:
		await manager.start()
	except KeyboardInterrupt:
		await manager.stop()
	except Exception as e:
		print(f"🚨 [КРИТИЧЕСКИЙ СБОЙ]: {e}")
		await manager.stop()

if __name__ == "__main__":
	asyncio.run(main())
