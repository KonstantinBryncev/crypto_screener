import os
import sys
import asyncio
import logging

# Подтягиваем менеджер
from core.arbitrage_manager import ArbitrageManager

def load_config():
	"""Загрузка конфигурационного файла из папки config"""
	base_dir = os.path.dirname(os.path.abspath(__file__))
	config_path = os.path.join(base_dir, "config", "config_bot.json")
	if os.path.exists(config_path):
		with open(config_path, "r", encoding="utf-8") as f:
			return json.load(f)
	return {}

async def main():
	# Настраиваем логирование, чтобы видеть скрытые ошибки, если они появятся
	logging.basicConfig(level=logging.WARNING)
	
	config = load_config()
	if not config:
		print("🚨 [ОШИБКА] Главный файл конфигурации config_bot.json не найден!")
		sys.exit(1)
		
	# Запускаем скринер через полноценное ядро управления
	manager = ArbitrageManager(config)
	try:
		await manager.start()
	except KeyboardInterrupt:
		await manager.stop()
	except Exception as e:
		print(f"🚨 [КРИТИЧЕСКИЙ СБОЙ СИСТЕМЫ]: {e}")
		await manager.stop()

if __name__ == "__main__":
	# Настройка политики для Windows систем, чтобы не летели ошибки закрытия сокетов при тестах дома
	if sys.platform == 'win32':
		asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
		
	asyncio.run(main())
