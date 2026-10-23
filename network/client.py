# Модуль: network/client.py
import aiohttp
import asyncio

class AsyncHttpClient:
	"""
	Асинхронный HTTP-клиент (Синглтон) для отправки легких сетевых запросов.
	Обеспечивает повторное использование одного сессионного соединения.
	"""
	_instance = None

	def __new__(cls, *args, **kwargs):
		if not cls._instance:
			cls._instance = super(AsyncHttpClient, cls).__new__(cls, *args, **kwargs)
			cls._instance.session = None
		return cls._instance

	def get_session(self) -> aiohttp.ClientSession:
		"""
		Синхронный метод получения или инициализации асинхронной сессии.
		Гарантированно создает ClientSession и сохраняет его в self.session.
		"""
		if self.session is None or self.session.closed:
			self.session = aiohttp.ClientSession()
		return self.session

	async def fetch_json(self, url: str, params: dict = None, headers: dict = None) -> dict:
		"""
		Универсальный асинхронный метод для выполнения GET-запросов и получения JSON.
		"""
		current_session = self.get_session()

		try:
			async with current_session.get(url, params=params, headers=headers, timeout=10) as response:
				if response.status == 200:
					return await response.json()
				else:
					print(f"⚠️ [СЕТЬ] Ошибка запроса к {url}: Статус {response.status}")
					return {}
		except Exception as e:
			print(f"⚠️ [СЕТЬ] Не удалось выполнить запрос к {url}: {e}")
			return {}

	def _get_random_proxy(self) -> str | None:
		"""
		Возвращает случайный прокси-сервер из списка для ротации.
		В данный момент возвращает None (прямое подключение).
		"""
		return None

	async def close(self):
		"""Корректное закрытие сессии при остановке приложения"""
		if self.session and not self.session.closed:
			await self.session.close()
			print("🔒 [СЕТЬ] Асинхронная сессия успешно закрыта.")
