# Файл: network/client.py
import asyncio
import logging
import os
import json
import random
import sys
from urllib.parse import urlparse, parse_qs, unquote
import aiohttp
from aiohttp_socks import ProxyConnector

logger = logging.getLogger("AsyncHttpClient")


class AsyncHttpClient:
	_instance = None

	def __new__(cls, *args, **kwargs):
		if not cls._instance:
			cls._instance = super(AsyncHttpClient, cls).__new__(cls)
		return cls._instance

	def __init__(self, config: dict):
		if hasattr(self, "_initialized"):
			return

		if not config:
			raise ValueError("🚨 [СЕТЬ] В AsyncHttpClient передан пустой словарь конфигурации!")

		self.config = config

		# Строго вычитываем все сетевые параметры из config/config.py без хардкода
		try:
			self.net_config = self.config["network"]
			self.proxies_raw_url = str(self.net_config["proxies_raw_url"])
			self.socks_port = int(self.net_config["local_socks_port"])
			self.dns_server = str(self.net_config["dns_server"])
			self.xray_bin = os.path.normpath(str(self.net_config["xray_bin_path"]))
			self.config_output_path = str(self.net_config["config_output_path"])
			self.enable_tunnel_on_windows = bool(self.net_config["enable_tunnel_on_windows"])
			self.http_total_timeout = float(self.net_config["http_total_timeout"])
			self.http_connect_timeout = float(self.net_config["http_connect_timeout"])
		except KeyError as e:
			raise ValueError(f"🚨 [КОНФИГ] В секции 'network' отсутствует обязательный ключ: {e}")

		self.vless_link = ""
		self.xray_process = None
		self.session = None
		self.tunnel_active = False
		self._initialized = True

	def _parse_vless_link(self) -> dict:
		"""Безопасный разбор VLESS-ссылки в словарь параметров для Xray."""
		try:
			if not self.vless_link or not self.vless_link.startswith("vless://"):
				return {}

			# Разделяем основную ссылку и имя конфигурации после #
			parts = self.vless_link.split("#")
			main_part = parts[0]
			remark = unquote(parts[1]) if len(parts) > 1 else "crypto-tunnel"

			parsed = urlparse(main_part)
			query_params = parse_qs(parsed.query)
			cleaned_params = {}

			for key, value in query_params.items():
				if value and isinstance(value, list):
					cleaned_params[key] = str(value[0]).strip()
				elif value:
					cleaned_params[key] = str(value).strip()

			return {
				"uuid": str(parsed.username) if parsed.username else "",
				"address": str(parsed.hostname) if parsed.hostname else "",
				"port": int(parsed.port) if parsed.port else 443,
				"params": cleaned_params,
				"remark": str(remark)
			}
		except Exception as e:
			logger.error(f"🚨 [СЕТЬ] Ошибка парсинга VLESS ссылки: {e}")
			return {}

	def _build_xray_config(self, parsed_data: dict) -> dict:
		"""Генерирует JSON-конфигурацию Xray под Reality-туннель."""
		params = parsed_data["params"]
		outbound_tag = "proxy"

		user_entry = {
			"id": parsed_data["uuid"],
			"encryption": "none"
		}

		if params.get("flow"):
			user_entry["flow"] = str(params.get("flow")).strip()

		outbound_settings = {
			"vnext": [{
				"address": parsed_data["address"],
				"port": parsed_data["port"],
				"users": [user_entry]
			}]
		}

		stream_settings = {
			"network": params.get("type", "tcp"),
			"security": params.get("security", "none")
		}

		if params.get("security") == "reality":
			stream_settings["realitySettings"] = {
				"show": False,
				"serverName": params.get("sni", ""),
				"publicKey": params.get("pbk", ""),
				"shortId": params.get("sid", ""),
				"fingerprint": params.get("fp", "chrome")
			}

		dns_config = {
			"disableCache": False,
			"disableFallback": True,
			"servers": [{"address": self.dns_server, "port": 53, "outbound": outbound_tag}]
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
				{"tag": outbound_tag, "protocol": "vless", "settings": outbound_settings, "streamSettings": stream_settings},
				{"tag": "direct", "protocol": "freedom", "settings": {}}
			],
			"routing": {
				"domainStrategy": "AsIs",
				"rules": [{"type": "field", "inboundTag": ["socks"], "port": 53, "outboundTag": outbound_tag}]
			}
		}

	async def init_tunnel(self) -> bool:
		"""
		Запускает Xray-туннель на Linux VPS.
		На Windows при enable_tunnel_on_windows=False полностью пропускает запуск и не трогает порты.
		"""
		if sys.platform == "win32" and not self.enable_tunnel_on_windows:
			self.tunnel_active = False
			print("🖥️  [СЕТЬ] Работаем на Windows: запуск Xray-туннеля отключен в конфиге, идем напрямую.", flush=True)
			return False

		# Зачищаем старые процессы Xray на Linux-сервере
		try:
			if sys.platform != "win32":
				os.system("pkill -f xray 2>/dev/null")
				await asyncio.sleep(0.5)
		except Exception as e:
			logger.warning(f"⚠️ [СЕТЬ] Не удалось выполнить зачистку процессов xray: {e}")

		# Скачиваем актуальный VLESS-ключ из источника в config/config.py
		try:
			timeout = aiohttp.ClientTimeout(total=self.http_total_timeout)
			async with aiohttp.ClientSession(timeout=timeout) as download_session:
				async with download_session.get(self.proxies_raw_url) as resp:
					if resp.status == 200:
						text_data = await resp.text()
						lines = [line.strip() for line in text_data.split("\n") if line.strip().startswith("vless://")]
						if lines:
							self.vless_link = random.choice(lines)
							logger.info(f"✅ [СЕТЬ] Загружен VLESS-ключ: {self.vless_link[:45]}...")
		except Exception as e:
			logger.error(f"🚨 [СЕТЬ] Ошибка скачивания списка VLESS: {e}")

		if not self.vless_link:
			self.tunnel_active = False
			logger.warning("⚠️ [СЕТЬ] VLESS-ключ не получен. Работаем напрямую без туннеля.")
			return False

		config_data = self._parse_vless_link()
		if not config_data or not config_data.get("uuid"):
			self.tunnel_active = False
			logger.error("🚨 [СЕТЬ] Ошибка парсинга VLESS-ссылки.")
			return False

		xray_json = self._build_xray_config(config_data)
		with open(self.config_output_path, "w", encoding="utf-8") as file:
			json.dump(xray_json, file, indent=4, ensure_ascii=False)

		try:
			self.xray_process = await asyncio.create_subprocess_exec(
				self.xray_bin, "run", "-c", self.config_output_path,
				stdout=asyncio.subprocess.DEVNULL,
				stderr=asyncio.subprocess.DEVNULL
			)
			self.tunnel_active = True

			# Если HTTP-сессия уже была создана ранее — закрываем ее, чтобы пересоздать через новый SOCKS5-порт
			if self.session and not self.session.closed:
				await self.session.close()
				self.session = None

			return True
		except Exception as e:
			self.tunnel_active = False
			logger.error(f"🚨 [СЕТЬ] Ошибка запуска ядра Xray: {e}")
			return False

	async def get_session(self) -> aiohttp.ClientSession:
		"""Возвращает активную HTTP-сессию (через SOCKS5 на VPS или напрямую на Windows)."""
		if self.session and not self.session.closed:
			return self.session

		headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

		if self.tunnel_active:
			proxy_url = f"socks5://127.0.0.1:{self.socks_port}"
			connector = ProxyConnector.from_url(proxy_url)
			self.session = aiohttp.ClientSession(connector=connector, headers=headers)
		else:
			self.session = aiohttp.ClientSession(headers=headers)

		return self.session

	async def fetch_json(self, url: str, method: str = "GET", **kwargs) -> dict:
		"""Выполняет асинхронный HTTP-запрос и возвращает распарсенный JSON."""
		session = await self.get_session()
		timeout = aiohttp.ClientTimeout(
			total=self.http_total_timeout,
			connect=self.http_connect_timeout,
			sock_connect=self.http_connect_timeout,
			sock_read=self.http_connect_timeout
		)

		try:
			async with session.request(method, url, timeout=timeout, **kwargs) as response:
				if response.status == 200:
					return await response.json()
				logger.warning(f"⚠️ [СЕТЬ] Неуспешный статус {response.status} при запросе {url}")
				return None
		except Exception as e:
			logger.error(f"🚨 [СЕТЬ] Сбой запроса {url}: {e}")
			return None

	async def close(self):
		"""Корректно закрывает HTTP-сессию и останавливает процесс Xray при выходе."""
		if self.session and not self.session.closed:
			await self.session.close()
			self.session = None

		if self.xray_process:
			try:
				self.xray_process.terminate()
				await self.xray_process.wait()
			except Exception as e:
				logger.warning(f"⚠️ [СЕТЬ] Ошибка остановки процесса Xray: {e}")
			finally:
				self.xray_process = None
				self.tunnel_active = False
