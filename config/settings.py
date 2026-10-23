# Модуль: config/settings.py
import os
from pathlib import Path
from dotenv import load_dotenv

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

