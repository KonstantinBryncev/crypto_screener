# Файл: network/client.py
import asyncio
import aiohttp
import logging
import os
import json
import subprocess
import sys
import socket
from typing import Optional, Any, List
from urllib.parse import unquote, urlparse, parse_qs

# Импорт библиотеки маскировки для Reality-туннелей
from curl_cffi.requests import AsyncSession  

logger = logging.getLogger("AsyncHttpClient")

class AsyncHttpClient:
	"""
	Оптимизированный HTTP-клиент (Singleton).
	Интегрирует ядро Xray, динамически подбирает порты и полностью
	маскирует запросы к Gate.io, OKX и KuCoin под Chrome через Reality-туннель.
	"""
	_instance = None

	def __new__(cls, *args, **kwargs):
		if not cls._instance:
			cls._instance = super(AsyncHttpClient, cls).__new__(cls, *args, **kwargs)
			cls._instance.session = None
			cls._instance.xray_process = None
			cls._instance.local_port = None
			cls._instance.internal_proxy_url = None
			
			current_dir = os.path.dirname(os.path.abspath(__file__))
			project_root = os.path.dirname(current_dir)
			cls._instance.config_path = os.path.join(project_root, "config", "config_bot.json")
			
			cls._instance._start_integrated_xray_vpn()
		return cls._instance

	def _find_free_port(self) -> int:
		"""Динамический поиск свободного порта в системе"""
		try:
			with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
				s.bind(('127.0.0.1', 0))
				return s.getsockname()[1]
		except Exception as e:
			logger.error(f"Не удалось динамически найти порт: {e}. Берем резервный.")
			return 10808

	def _start_integrated_xray_vpn(self):
		"""Парсинг VLESS, генерация чистого JSON и запуск ядра Xray"""
		if not os.path.exists(self.config_path):
			print(f"⚠️ [СЕТЬ] Главный файл конфигурации {self.config_path} не найден! VPN не запущен.")
			return

		try:
			with open(self.config_path, "r", encoding="utf-8") as f:
				bot_config = json.load(f)
			
			net_settings = bot_config.get("network", {})
			vless_link = net_settings.get("vless_link")
			
			if not vless_link or "ВАША_" in vless_link:
				print("⚠️ [СЕТЬ] VLESS ссылка не настроена. Скринер работает в прямом сетевом режиме.")
				return

			project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
			xray_bin = os.path.normpath(os.path.join(project_root, net_settings.get("xray_bin_path", "bin/xray.exe")))
			config_output = os.path.join(project_root, net_settings.get("config_output_path", "config.json"))

			self.local_port = self._find_free_port()
			
			parsed = urlparse(vless_link)
			query_params = parse_qs(parsed.query)
			cleaned_params = {k: v[0] for k, v in query_params.items() if v}

			outbound_tag = "proxy"
			stream_settings = {
				"network": cleaned_params.get("type", "tcp"),
				"security": cleaned_params.get("security", "none")
			}
			
			if cleaned_params.get("security") == "reality":
				stream_settings["realitySettings"] = {
					"show": False,
					"serverName": cleaned_params.get("sni", ""),
					"publicKey": cleaned_params.get("pbk", ""),
					"shortId": cleaned_params.get("sid", ""),
					"fingerprint": cleaned_params.get("fp", "chrome")
				}
				
			if cleaned_params.get("type") == "grpc":
				stream_settings["grpcSettings"] = {"serviceName": cleaned_params.get("serviceName", "")}

			xray_config = {
				"log": {"loglevel": "warning"},
				"dns": {
					"disableCache": False,
					"disableFallback": True,
					"servers": [{"address": "https://1.1.1", "port": 53, "outbound": outbound_tag}]
				},
				"inbounds": [{
					"port": self.local_port,
					"listen": "127.0.0.1",
					"protocol": "socks",
					"settings": {"auth": "noauth", "udp": True},
					"sniffing": {"enabled": True, "destOverride": ["http", "tls", "quic"], "metadataOnly": False}
				}],
				"outbounds": [
					{"tag": outbound_tag, "protocol": "vless", "settings": {"vnext": [{"address": parsed.hostname, "port": parsed.port, "users": [{"id": parsed.username, "encryption": "none"}]}]}, "streamSettings": stream_settings},
					{"tag": "direct", "protocol": "freedom", "settings": {}}
				],
				"routing": {"domainStrategy": "AsIs", "rules": [{"type": "field", "inboundTag": ["socks"], "port": 53, "outboundTag": outbound_tag}]}
			}

			with open(config_output, "w", encoding="utf-8") as f:
				json.dump(xray_config, f, indent=4, ensure_ascii=False)

			if not os.path.exists(xray_bin):
				print(f"❌ [СЕТЬ] Исполняемый файл ядра Xray отсутствует: {xray_bin}")
				return

			self.xray_process = subprocess.Popen(
				[xray_bin, "run", "-c", config_output],
				stdout=subprocess.DEVNULL,
				stderr=subprocess.DEVNULL
			)
			
			self.internal_proxy_url = f"socks5h://127.0.0.1:{self.local_port}"
			print(f"🔒 [СЕТЬ] Локальный ВПН-шлюз успешно поднят на порту {self.local_port} (PID: {self.xray_process.pid})")

		except Exception as e:
			print(f"🚨 [СЕТЬ] Ошибка автозапуска ядра Xray: {e}")

	async def get_session(self) -> aiohttp.ClientSession:
		"""Легкая общая асинхронная сессия для Bybit/BingX"""
		if self.session is None or self.session.closed:
			timeout = aiohttp.ClientTimeout(total=10, connect=4)
			headers = {
				"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
				"Accept": "application/json"
			}
			
			if self.internal_proxy_url:
				try:
					from aiohttp_socks import ProxyConnector
					connector = ProxyConnector.from_url(self.internal_proxy_url)
					self.session = aiohttp.ClientSession(timeout=timeout, headers=headers, connector=connector)
				except ImportError:
					self.session = aiohttp.ClientSession(timeout=timeout, headers=headers)
			else:
				self.session = aiohttp.ClientSession(timeout=timeout, headers=headers)
				
		return self.session

	async def fetch_json(
		self, 
		url: str, 
		method: str = "GET", 
		params: Optional[dict] = None, 
		headers: Optional[dict] = None, 
		data: Optional[Any] = None
	) -> Optional[dict]:
		"""Центральный диспетчер запросов бота"""
		request_headers = {
			"Accept": "application/json",
			"Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8"
		}
		if headers:
			for k, v in headers.items():
				request_headers[str(k)] = str(v)

		# =========================================================================
		# ТОЧЕЧНЫЙ ПЕРЕХВАТ ПЛАТФОРМ (ПРОБИВАЕМ РКН И КЛАУДФЛЕЕР ЧЕРЕЗ REALITY)
		# =========================================================================
		target_domains = ["gateio", "gate.io", "okx", "kucoin", "telegram.org"]
		if any(domain in url for domain in target_domains):
			try:
				async with AsyncSession(impersonate="chrome120") as crypto_session:
					response = await crypto_session.request(
						method=method,
						url=url,
						params=params,
						headers=request_headers,
						data=data,
						proxy=self.internal_proxy_url,  # Наш зашифрованный туннель
						timeout=8
					)
					
					if response.status_code != 200:
						return None
					return response.json()
			except Exception as e:
				logger.error(f"🚨 [ТУННЕЛЬ REALITY] Сбой запроса на {url}: {e}")
				return None

		# =========================================================================
		# СТАНДАРТНЫЙ ПУТЬ ДЛЯ ОСТАЛЬНЫХ БИРЖ (BYBIT, BINGX)
		# =========================================================================
		session = await self.get_session()
		try:
			async with session.request(
				method=method,
				url=url,
				params=params,
				headers=request_headers,
				data=data,
				timeout=aiohttp.ClientTimeout(total=6)
			) as response:
				if response.status != 200:
					return None
				return await response.json()
		except Exception as e:
			logger.error(f"🚨 [СЕТЬ ОШИБКА] Сбой запроса к {url}: {e}")
			return None

	async def close(self):
		"""Безопасная остановка сессий и выгрузка xray.exe из памяти ОС"""
		if self.session and not self.session.closed:
			await self.session.close()
		if self.xray_process:
			print(f"🛑 [СЕТЬ] Выгружаем фоновый процесс ядра Xray (PID: {self.xray_process.pid})...")
			self.xray_process.terminate()
			self.xray_process.wait()
		print("🔒 [СЕТЬ] Все сетевые сессии и туннели успешно закрыты.")
