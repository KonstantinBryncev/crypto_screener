# Модуль: network/client.py
import asyncio
import random
from typing import Optional, List
import aiohttp
from aiohttp_socks import ProxyConnector
from config import settings

class AsyncHttpClient:
	# _instance хранит в себе единственный созданный объект этого класса.
	# Это нужно для реализации паттерна "Синглтон" (Singleton).
	_instance: Optional['AsyncHttpClient'] = None
	
	def __new__(cls, *args, **kwargs):
		"""
		__new__ — это метод, который вызывается ДО создания объекта (__init__).
		Здесь мы проверяем: если мы РАНИЕ уже создавали этот клиент, то мы не создаем
		новый, а возвращаем старый. В итоге во всем боте будет существовать строго 
		ОДНА сетевая сессия. Это экономит оперативную память и не нагружает процессор 
		десятками одновременных переподключений.
		"""
		if cls._instance is None:
			cls._instance = super().__new__(cls)
			cls._instance._initialized = False
		return cls._instance

	def __init__(self):
		"""
		Конструктор класса. Из-за Синглтона мы проверяем флаг _initialized,
		чтобы код инициализации не запускался повторно при случайном вызове AsyncHttpClient().
		"""
		if self._initialized:
			return
			
		# Сюда мы сохраним объект сессии aiohttp, когда запустим первый запрос
		self.session: Optional[aiohttp.ClientSession] = None
		
		# Список строк, где будут храниться считанные из файла прокси
		self.proxies: List[str] = []
		
		# Ставим флаг в True, чтобы больше этот код не выполнялся
		self._initialized = True
		
		# Сразу при старте бота считываем файл config/proxies.txt в память
		self._load_proxies()

	def _load_proxies(self):
		"""
		Этот метод читает текстовый файл с прокси-серверами.
		Он написан "безопасно": если файла нет, бот не вылетит с ошибкой,
		а просто сам создаст пустой файл и продолжит работу напрямую.
		"""
		proxies_file = settings.PROXIES_FILE
		
		# Проверяем, существует ли файл proxies.txt
		if not proxies_file.exists():
			# Если папки config или файла нет — создаем их автоматически
			proxies_file.parent.mkdir(parents=True, exist_ok=True)
			proxies_file.touch()
			return

		# Открываем файл для чтения с указанием кодировки utf-8
		with open(proxies_file, "r", encoding="utf-8") as f:
			for line in f:
				# Очищаем строку от пробелов и знаков переноса строки (\n) по краям
				line = line.strip()
				
				# Проверяем, что строка не пустая и не является комментарием (не начинается с #)
				if line and not line.startswith("#"):
					self.proxies.append(line)
		
		# Если в списке появились прокси — выводим лог в консоль
		if self.proxies:
			print(f"🌐 [СЕТЬ] Загружено прокси из файла: {len(self.proxies)}")

	def _get_random_proxy(self) -> Optional[str]:
		"""
		Метод ротации прокси. Если в списке proxies есть адреса,
		функция выбирает один случайный для каждого нового запроса.
		Это называется "ротацией", чтобы биржа не заблокировала твой IP за частые запросы.
		"""
		if self.proxies:
			return random.choice(self.proxies)
		return None

	async def get_session(self) -> aiohttp.ClientSession:
		"""
		Этот метод гарантирует, что у нас всегда есть живое асинхронное соединение.
		Если сессия еще не создана или была закрыта — мы создаем её заново.
		"""
		if self.session is None or self.session.closed:
			# Задаем жесткий лимит времени на ожидание ответа от биржи (из config/settings.py).
			# Если биржа «зависнет», наш бот не будет ждать бесконечно и не сожрет процессор,
			# а просто сбросит этот запрос через 10 секунд и пойдет дальше.
			timeout = aiohttp.ClientTimeout(total=settings.REQUEST_TIMEOUT)
			
			# Инициализируем сессию aiohttp с нашим таймаутом
			self.session = aiohttp.ClientSession(timeout=timeout)
			print("🚀 [СЕТЬ] Асинхронная сессия успешно создана.")
		return self.session

	async def fetch_json(self, url: str, params: Optional[dict] = None) -> Optional[dict]:
		"""
		Универсальная асинхронная функция для отправки GET-запросов.
		Она пригодится нам для отправки алертов в Telegram или легких проверок.
		"""
		# Получаем нашу единую сессию
		session = await self.get_session()
		
		# Берем случайный прокси (если они записаны в файле)
		proxy = self._get_random_proxy()
		
		# Готовим аргументы для запроса (например, параметры URL)
		kwargs = {"params": params}
		
		if proxy:
			# Специфика aiohttp: обычные HTTP-прокси можно передавать строкой.
			# Но если ты поднимешь быстрый SOCKS5 прокси, aiohttp встроенно с ним работать не умеет.
			# Для этого мы используем библиотеку aiohttp-socks.
			if proxy.startswith("socks"):
				# Создаем специальный коннектор-переходник для SOCKS протокола
				connector = ProxyConnector.from_url(proxy)
				
				# Создаем временную сессию чисто под этот SOCKS-запрос
				async with aiohttp.ClientSession(connector=connector, timeout=session.timeout) as temp_session:
					async with temp_session.get(url) as response:
						if response.status == 200:
							return await response.json()
						return None
			else:
				# Если прокси обычный (http://), просто подмешиваем его в аргументы запроса
				kwargs["proxy"] = proxy

		try:
			# async with означает асинхронный контекстный менеджер.
			# В этот момент программа отправляет запрос в сеть и "засыпает" (уступает место другим задачам),
			# пока сервер биржи не пришлет ответ. Процессор в этот момент абсолютно свободен!
			async with session.get(url, **kwargs) as response:
				if response.status == 200:
					# Асинхронно читаем и парсим JSON ответ от сервера
					return await response.json()
				print(f"⚠️ [СЕТЬ] Ошибка запроса к {url}: Статус {response.status}")
				return None
		except Exception as e:
			# Если оборвался интернет или упал прокси — бот не упадет, а мягко обработает ошибку в лог
			print(f"❌ [СЕТЬ] Ошибка сети при запросе к {url}: {e}")
			return None

	async def close(self):
		"""
		Этот метод нужно вызвать при закрытии бота (в файле main.py).
		Он аккуратно освобождает сетевые порты Windows и закрывает соединения.
		"""
		if self.session and not self.session.closed:
			await self.session.close()
			print("🛑 [СЕТЬ] Асинхронная сессия закрыта.")
