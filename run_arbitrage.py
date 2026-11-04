# run_arbitrage.py
# run_arbitrage.py
import sys
import asyncio  # <-- ВОТ ЭТУ СТРОКУ НУЖНО ДОБАВИТЬ СЮДА
import logging
import warnings
import os
import json
from core.arbitrage_manager import ArbitrageManager
from network.client import AsyncHttpClient

# ОТКЛЮЧЕНИЕ ШУМА В ЛОГАХ БИБЛИОТЕК
logging.getLogger("asyncio").setLevel(logging.CRITICAL)
logging.getLogger("urllib3").setLevel(logging.CRITICAL)
warnings.filterwarnings("ignore")

async def main():
	"""
	Главная асинхронная точка входа в скринер межбиржевого арбитража.
	Подключает сетевые сессии и координирует запуск всех модулей.
	"""
	# Принудительный сброс буфера (flush=True) для мгновенного вывода в screen / ConEmu
	print("==================================================", flush=True)
	print("        ЗАПУСК: МЕЖБИРЖЕВОЙ АРБИТРАЖНЫЙ СКРИНЕР   ", flush=True)
	print("==================================================", flush=True)
	
	print("🔍 [ШАГ 0] Чтение конфигурации из папки config...", flush=True)
	# Получаем путь к папке, где лежит этот скрипт (crypto_screener)
	base_dir = os.path.dirname(os.path.abspath(__file__))
	# Формируем точный путь к файлу: crypto_screener/config/config_bot.json
	config_path = os.path.join(base_dir, "config", "config_bot.json")
	
	arb_settings = {}
	try:
		with open(config_path, "r", encoding="utf-8") as f:
			arb_settings = json.load(f)
		print(f"✅ [УСПЕХ] Конфигурация загружена из: {config_path}", flush=True)
	except FileNotFoundError:
		print(f"🚨 [КРИТ ОШИБКА] Файл настроек не найден по пути: {config_path}", flush=True)
		print("Проверьте, что файл config_bot.json переложен в нужную папку.", flush=True)
		return
	except json.JSONDecodeError as json_err:
		print(f"🚨 [КРИТ ОШИБКА] Ошибка синтаксиса JSON в файле конфигурации: {json_err}", flush=True)
		return

	print("🔍 [ШАГ 1] Инициализация HTTP-клиента и сессий...", flush=True)
	# Инициализируем синглтон HTTP клиента, чтобы он подтянул proxies.txt
	http_client = AsyncHttpClient()
	
	print("🔍 [ШАГ 2] Инициализация класса ArbitrageManager...", flush=True)
	# Передаем загруженный словарь с настройками прямо в конструктор менеджера
	manager = ArbitrageManager(arb_settings)
	
	print("🔍 [ШАГ 3] Запуск асинхронного цикла скринера...", flush=True)
	try:
		# Запускаем бесконечный цикл опроса стаканов бирж и отправку аларма старта в ТГ
		await manager.start()
	except KeyboardInterrupt:
		print("\n[MAIN] Завершение работы пользователем через сочетание клавиш...", flush=True)
	except Exception as loop_err:
		print(f"\n🚨 [MAIN КРИТ ОШИБКА] Непредвиденный сбой в работе ядра: {loop_err}", flush=True)
	finally:
		# Гарантированно отправляем алерт остановки в ТГ и закрываем ClientSession
		print("\n🔍 [ШАГ 4] Корректное закрытие сетевых коннектов...", flush=True)
		await manager.stop()
		print("==================================================", flush=True)

if __name__ == "__main__":
	# Корректная настройка политики циклов для Windows платформ разработки
	if sys.platform == 'win32':
		asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
		
	try:
		asyncio.run(main())
	except KeyboardInterrupt:
		pass
