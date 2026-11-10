# Файл: network/client.py
import asyncio
import logging
import os
import json
import sys
from urllib.parse import urlparse, parse_qs, unquote
import aiohttp
from aiohttp_socks import ProxyConnector

logger = logging.getLogger("AsyncHttpClient")

class AsyncHttpClient:
	"""
	Универсальный асинхронный сетевой клиент для торгового бота.
	Автоматически разворачивает изолированный туннель Xray-core с защитой DNS.
	"""
	_instance = None

	def __new__(cls, *args, **kwargs):
		if not cls._instance:
			cls._instance = super(AsyncHttpClient, cls).__new__(cls)
		return cls._instance

	def __init__(self, config: dict = None):
		if hasattr(self, "_initialized"):
			return
		self.config = config or {}
		self.net_config = self.config.get("network", {})
		
		# Загружаем параметры (приоритет из config_bot.json, иначе дефолты)
		self.vless_link = self.net_config.get("vless_link", "")
		self.socks_port = int(self.net_config.get("local_socks_port", 52115))
		
		# Адаптируем пути под Linux (убираем .exe, если скрипт на сервере)
		bin_path = self.net_config.get("xray_bin_path", "bin/xray")
		if sys.platform != "win32" and bin_path.endswith(".exe"):
			bin_path = bin_path.replace(".exe", "")
		self.xray_bin = os.path.normpath(bin_path)
		
		self.config_output_path = self.net_config.get("config_output_path", "config.json")
		self.xray_process = None
		self.session = None
		self._initialized = True

	def _parse_vless_link(self) -> dict:
		"""Разбирает vless:// на чистые строковые параметры сети"""
		try:
			if not self.vless_link.startswith("vless://"):
				return {}
			
			cleaned_link = self.vless_link.split("#")
			parsed = urlparse(cleaned_link)
			
			query_params = parse_qs(parsed.query)
			cleaned_params = {}
			for key, value in query_params.items():
				if value:
					cleaned_params[key] = value[0]

			return {
				"uuid": parsed.username,
				"address": parsed.hostname,
				"port": int(parsed.port) if parsed.port else 443,
				"params": cleaned_params,
				"remark": unquote(parsed.fragment) if parsed.fragment else "crypto-tunnel"
			}
		except Exception as e:
			logger.error(f"Ошибка парсинга VLESS ссылки: {e}")
			return {}

	def _build_xray_config(self, parsed_data: dict) -> dict:
		"""Генерирует полную защищенную конфигурацию Xray с Anti-DNS Leak"""
		params = parsed_data["params"]
		OUTBOUND_TAG = "proxy"

		# Базовые настройки исходящего прокси-соединения
		outbound_settings = {
			"vnext": [{
				"address": parsed_data["address"],
				"port": parsed_data["port"],
				"users": [{
					"id": parsed_data["uuid"],
					"encryption": "none"
				}]
			}]
		}

		# Внедряем параметр flow (КРИТИЧНО для xtls-rprx-vision!)
		if params.get("flow"):
			outbound_settings["vnext"][0]["users"][0]["flow"] = params.get("flow")

		stream_settings = {
			"network": params.get("type", "tcp"),
			"security": params.get("security", "none")
		}

		# Настройка параметров маскировки Reality
		if params.get("security") == "reality":
			stream_settings["realitySettings"] = {
				"show": False,
				"serverName": params.get("sni", ""),
				"publicKey": params.get("pbk", ""),
				"shortId": params.get("sid", ""),
				"fingerprint": params.get("fp", "chrome")
			}

		# Поддержка различных типов транспорта транспорта (gRPC / WS)
		if params.get("type") == "grpc":
			stream_settings["grpcSettings"] = {"serviceName": params.get("serviceName", "")}
		elif params.get("type") == "ws":
			stream_settings["wsSettings"] = {
				"path": params.get("path", "/"),
				"headers": {"Host": params.get("sni", "")}
			}

		# Безопасный DNS для исключения блокировок Cloudflare на подлете
		dns_config = {
			"disableCache": False,
			"disableFallback": True,
			"servers": [{"address": "https://1.1.1", "port": 53, "outbound": OUTBOUND_TAG}]
		}

		return {
			"log": {"loglevel": "warning"},
			"dns": dns_config,
			"inbounds": [{
				"port": self.socks_port,
				"listen": "127.0.0.1",
				"protocol": "socks",
				"settings": {"auth": "noauth", "udp": True},
				"sniffing": {"enabled": True, "destOverride": ["http", "tls", "quic"], "metadataOnly": False}
			}],
			"outbounds": [
				{"tag": OUTBOUND_TAG, "protocol": "vless", "settings": outbound_settings, "streamSettings": stream_settings},
				{"tag": "direct", "protocol": "freedom", "settings": {}}
			],
			"routing": {
				"domainStrategy": "AsIs",
				"rules": [{"type": "field", "inboundTag": ["socks"], "port": 53, "outboundTag": OUTBOUND_TAG}]
			}
		}

	async def init_tunnel(self) -> bool:
		"""Запускает защищенный фоновый процесс Xray-core на сервере"""
		if not self.vless_link:
			print("▲ [СЕТЬ] VPN отключен. Скринер работает напрямую.")
			return False

		config_data = self._parse_vless_link()
		if not config_data:
			print("🚨 [СЕТЬ] Ошибка разбора ссылки туннеля.")
			return False

		xray_json = self._build_xray_config(config_data)

		with open(self.config_output_path, "w", encoding="utf-8") as file:
			json.dump(xray_json, file, indent=4, ensure_ascii=False)

		# На Linux принудительно выдаем права бинарнику на выполнение
		if sys.platform != "win32" and os.path.exists(self.xray_bin):
			os.chmod(self.xray_bin, 0o755)

		try:
			# Запуск ядра в фоне
			self.xray_process = await asyncio.create_subprocess_exec(
				self.xray_bin, "run", "-c", self.config_output_path,
				stdout=asyncio.subprocess.DEVNULL,
				stderr=asyncio.subprocess.DEVNULL
			)
			print(f"🔒 [СЕТЬ] Локальный ВПН-шлюз успешно поднят на порту {self.socks_port} (PID: {self.xray_process.pid})")
			await asyncio.sleep(2.5)  # Даем время ядру зацепиться за прокси
			return True
		except Exception as e:
			print(f"🚨 [СЕТЬ] Ошибка инициализации ядра Xray: {e}")
			return False

	async def get_session(self) -> aiohttp.ClientSession:
		"""Генерирует сессию, обернутую в локальный SOCKS5 прокси"""
		if self.session and not self.session.closed:
			return self.session

		headers = {
			"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
		}

		if self.vless_link and self.xray_process:
			proxy_url = f"socks5://127.0.0.1:{self.socks_port}"
			connector = ProxyConnector.from_url(proxy_url)
			self.session = aiohttp.ClientSession(connector=connector, headers=headers)
		else:
			self.session = aiohttp.ClientSession(headers=headers)
		return self.session

	async def fetch_json(self, url: str) -> dict:
		"""Безопасно вытягивает JSON стаканов через туннель"""
		session = await self.get_session()
		try:
			async with session.get(url, timeout=4) as response:
				if response.status == 200:
					return await response.json()
				return None
		except Exception:
			return None

	async def close(self):
		"""Чистит сессии и процессы при остановке бота"""
		if self.session and not self.session.closed:
			await self.session.close()
		if self.xray_process:
			try:
				self.xray_process.terminate()
				await self.xray_process.wait()
				print("🔒 [СЕТЬ] Локальный ВПН-шлюз Xray успешно остановлен.")
			except Exception:
				pass
