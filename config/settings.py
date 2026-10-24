# Модуль: config/settings.py
import os
from pathlib import Path
from dotenv import load_dotenv
import json

# Определяем базовый путь к проекту
BASE_DIR = Path(__file__).resolve().parent.parent

# Загружаем переменные окружения из файла .env
load_dotenv(BASE_DIR / ".env")

# API Настройки Bybit
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY", "")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET", "")

# Telegram Настройки
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Настройки скринера
SCAN_INTERVAL = 10      # Интервал опроса биржи в секундах (для REST API)
REQUEST_TIMEOUT = 10    # Таймаут сетевых запросов в секундах
MAX_TIMESTAMPS = 60     # Сколько исторических точек хранить для каждой монеты (вместо pandas)

# Пути к системным файлам (ИМЕННО ЭТА СТРОКА СЕЙЧАС НУЖНА КЛИЕНТУ)
PROXIES_FILE = BASE_DIR / "config" / "proxies.txt"

# Путь к файлу с историей аномалий
SIGNALS_CSV_FILE = BASE_DIR / "database" / "signals_history.csv"

# Настройки фильтрации
MIN_24H_VOLUME_USDT = 50000.0  # Игнорировать монеты с суточным объемом меньше $50,000



# Базовый интервал опроса по умолчанию (если вдруг json не прочитается)
SCAN_INTERVAL = 10.0

def load_bot_config() -> dict:
    """Загружает динамические настройки скринеров из JSON файла"""
    # Вычисляем путь к файлу config_bot.json относительно текущего файла
    current_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(current_dir, "config_bot.json")
    
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"❌ Файл настроек не найден по пути: {config_path}")
        
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)

