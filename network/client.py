import asyncio
import aiohttp
import random
from typing import Optional, List

class AsyncHttpClient:
	_instance = None

	def __new__(cls, *args, **kwargs):
		if not cls._instance:
			cls._instance = super(AsyncHttpClient, cls).__new__(cls, *args, **kwargs)
			cls._instance.session = None
			cls._instance.proxies: List[str] = [] 
		return cls._instance

	def _get_random_proxy(self) -> Optional[str]:
		if self.proxies:
			return random.choice(self.proxies)
		return None

	async def get_session(self) -> aiohttp.ClientSession:
		"""Инициализирует сессию aiohttp с подменой заголовков браузера"""
		if self.session is None or self.session.closed:
			timeout = aiohttp.ClientTimeout(total=15, connect=5)
			
			# МАСКИРОВКА: Добавляем стандартные заголовки Chrome, чтобы Cloudflare не выдавал 403
			headers = {
				"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
				"Accept": "application/json",
				"Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"
			}
			
			self.session = aiohttp.ClientSession(timeout=timeout, headers=headers)
		return self.session

	async def fetch_json(self, url: str, params: Optional[dict] = None, headers: Optional[dict] = None) -> Optional[dict]:
		"""
		Диагностический метод для отправки асинхронных GET-запросов.
		"""
		session = await self.get_session()
		proxy = self._get_random_proxy()
		try:
			async with session.get(url, params=params, headers=headers, proxy=proxy, timeout=10) as response:
				if response.status != 200:
					raw_text = await response.text()
					print(f"⚠️ [СЕТЬ ОТЛАДКА] URL: {url} | HTTP Статус: {response.status} | Ответ: {raw_text[:150]}")
					return None
					
				return await response.json()
		except Exception as network_error:
			print(f"🚨 [СЕТЬ КРИТИЧЕСКАЯ ОШИБКА] URL: {url} | Ошибка: {network_error}")
			return None

	async def close(self):
		if self.session and not self.session.closed:
			await self.session.close()
