import asyncio
import aiohttp
import random
import logging
from typing import Optional, List, Dict, Any
# Импортируем curl_cffi для идеального обхода систем защиты TLS Fingerprinting
from curl_cffi.requests import AsyncSession

logger = logging.getLogger("AsyncHttpClient")

class AsyncHttpClient:
	"""
	Асинхронный HTTP-клиент Одиночка (Singleton).
	Обеспечивает общую сессию aiohttp для Bybit/KuCoin/BingX,
	и использует curl_cffi для обхода жесткого WAF Cloudflare у Gate.io.
	"""
	_instance = None

	def __new__(cls, *args, **kwargs):
		if not cls._instance:
			cls._instance = super(AsyncHttpClient, cls).__new__(cls, *args, **kwargs)
			cls._instance.session = None
			cls._instance.proxies = [] 
		return cls._instance

	def _get_random_proxy(self) -> Optional[str]:
		if self.proxies:
			return random.choice(self.proxies)
		return None

	async def get_session(self) -> aiohttp.ClientSession:
		if self.session is None or self.session.closed:
			timeout = aiohttp.ClientTimeout(total=15, connect=5)
			headers = {
				"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
				"Accept": "application/json",
				"Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
				"Connection": "keep-alive"
			}
			self.session = aiohttp.ClientSession(timeout=timeout, headers=headers)
		return self.session

		# =========================================================================
		# ТОЧЕЧНЫЙ ПЕРЕХВАТ И ФИЛЬТРАЦИЯ GATE.IO: ПОЛНАЯ ИМПЕРСОНАЦИЯ БРАУЗЕРА
		# =========================================================================
		if "gateio" in url or "gate.io" in url:
			try:
				# curl_cffi полностью маскирует TLS-отпечатки под десктопный Chrome 120
				async with AsyncSession(impersonate="chrome120") as curl_session:
					response = await curl_session.request(
						method=method,
						url=url,
						params=params,
						headers=headers, # Передаем заголовки без внутренних полей aiohttp
						proxy=proxy,
						timeout=10
					)
					if response.status_code != 200:
						return None
					return response.json()
			except Exception as e:
				logger.error(f"Сбой curl_cffi имперсонации для Gate.io: {e}")
				return None




		# СТАНДАРТНЫЙ ПУТЬ: Спокойный сбор данных для Bybit, KuCoin, BingX через aiohttp
		session = await self.get_session()
		request_headers = {
			"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
			"Accept": "application/json",
			"Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"
		}
		
		if headers is not None:
			for key, value in headers.items():
				request_headers[key] = value

		try:
			async with session.request(
				method=method,
				url=url,
				params=params,
				headers=request_headers,
				proxy=proxy,
				timeout=aiohttp.ClientTimeout(total=8)
			) as response:
				if response.status != 200:
					raw_text = await response.text()
					print(f"⚠️ [СЕТЬ ОТЛАДКА] URL: {url} | HTTP Статус: {response.status} | Ответ: {raw_text[:150]}", flush=True)
					return None
				return await response.json()
		except asyncio.TimeoutError:
			return None
		except Exception as network_error:
			print(f"🚨 [СЕТЬ ОШИБКА] URL: {url} | Сбой: {network_error}", flush=True)
			return None

	async def close(self):
		if self.session and not self.session.closed:
			await self.session.close()
			print("🛑 [СЕТЬ] Асинхронная сессия HttpClient успешно закрыта.")
