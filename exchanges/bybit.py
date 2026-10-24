# Модуль: exchanges/bybit.py
import os
import ccxt.pro as ccxt  # Асинхронная библиотека CCXT
from dotenv import load_dotenv  # Корректный импорт для загрузки переменных из .env

class BybitExchange:
	"""
	Класс для взаимодействия с биржей Bybit в реальном (Live) режиме.
	Ориентирован на работу со спотовым рынком.
	"""
	def __init__(self):
		self.api = None
		
		# Вычисляем абсолютный путь к файлу .env в корне проекта
		current_dir = os.path.dirname(os.path.abspath(__file__))
		project_root = os.path.dirname(current_dir)
		env_path = os.path.join(project_root, ".env")
		
		# Загружаем переменные из .env файла, если он существует
		if os.path.exists(env_path):
			load_dotenv(env_path)

	async def init_exchange(self):
		"""
		Инициализация асинхронного подключения к РЕАЛЬНЫМ (Live) серверам Bybit.
		"""
		# Вытаскиваем API-ключи из загруженного окружения
		api_key = os.getenv('BYBIT_API_KEY')
		secret_key = os.getenv('BYBIT_API_SECRET')
		
		# Создаем инстанс ccxt для реального спотового рынка
		self.api = ccxt.bybit({
			'apiKey': api_key if api_key else "",
			'secret': secret_key if secret_key else "",
			'enableRateLimit': True,
			'options': {
				'defaultType': 'spot'  # Принудительно работаем с обычным спотовым рынком
			}
		})
		
		# Если ключи отсутствуют, бот всё равно сможет читать публичные стаканы (Order Book),
		# но приватные методы (запрос баланса, выставление ордеров) работать не будут.
		if not api_key or not secret_key:
			print("⚠️ [BYBIT] Предупреждение: API-ключи не найдены в .env. Работа в публичном режиме.")

	async def fetch_tickers(self) -> dict:
		"""
		Публичный метод сбора текущих цен (типеров) для сигнального скринера пампов.
		Возвращает стандартизированный словарь цен.
		"""
		if not self.api:
			return {}
		try:
			# Запрашиваем тикеры только для спотового рынка
			tickers = await self.api.fetch_tickers(params={'category': 'spot'})
			result = {}
			for symbol, ticker in tickers.items():
				# Фильтруем только пары к USDT
				if symbol.endswith('/USDT') and ticker.get('last') is not None:
					result[symbol] = {
						'price': float(ticker['last']),
						'volume': float(ticker.get('baseVolume', 0.0)) if ticker.get('baseVolume') else 0.0
					}
			return result
		except Exception as e:
			# Тихо возвращаем пустой словарь при ошибках сети, чтобы не спамить в консоль
			return {}

	async def fetch_balance_usdt(self) -> float:
		"""
		Приватный метод запроса реального баланса спотового кошелька.
		Требует наличия корректных ключей в .env.
		"""
		if not self.api or not self.api.apiKey:
			return 0.0
		try:
			balance = await self.api.fetch_balance()
			return float(balance.get('USDT', {}).get('free', 0.0))
		except Exception:
			return 0.0

	async def close(self):
		"""
		Корректное закрытие асинхронных сетевых сессий (AIOHTTP под капотом CCXT).
		Предотвращает появление ошибок 'Unclosed client session' при остановке бота.
		"""
		if self.api:
			await self.api.close()
