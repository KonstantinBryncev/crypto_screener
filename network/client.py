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
		self.vless_link = self.net_config.get("vless_link", "")
		self.socks_port = int(self.net_config.get("local_socks_port", 52115))
		
		bin_path = self.net_config.get("xray_bin_path", "bin/xray")
		if sys.platform != "win32" and bin_path.endswith(".exe"):
			bin_path = bin_path.replace(".exe", "")
		self.xray_bin = os.path.normpath(bin_path)
		self.config_output_path = self.net_config.get("config_output_path", "config.json")
		self.xray_process = None
		self.session = None
		self._initialized = True

	def _parse_vless_link(self) -> dict:
		"""Ультра-безопасный парсер ссылки без использования .decode() и списков"""
		try:
			if not self.vless_link or not self.vless_link.startswith("vless://"):
				return {}
			
			# Разделяем ссылку и хэш-тег имени конфигурации
			parts = self.vless_link.split("#")
			main_part = parts[0]
			remark = unquote(parts[1]) if len(parts) > 1 else "crypto-tunnel"
			
			parsed = urlparse(main_part)
			query_params = parse_qs(parsed.query)
			cleaned_params = {}
			
			# Безопасное извлечение строк из списков параметров parse_qs
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
			logger.error(f"Ошибка парсинга VLESS ссылки: {e}")
			return {}

	def _build_xray_config(self, parsed_data: dict) -> dict:
		"""Генерирует полную конфигурацию Xray под Reality-туннель"""
		params = parsed_data["params"]
		OUTBOUND_TAG = "proxy"

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
			"servers": [{"address": "https://1.1.1", "port": 53, "outbound": OUTBOUND_TAG}]
		}

		return {
			"log": {"loglevel": "warning"},
			"dns": dns_config,
			"inbounds": [{
				"port": self.socks_port, "listen": "127.0.0.1", "protocol": "socks",
				"settings": {"auth": "noauth", "udp": True},
				"sniffing": {"enabled": True, "destOverride": ["http", "tls", "quic"], "metadataOnly": False}
			}],
			"outbounds": [
				{"tag": OUTBOUND_TAG, "protocol": "vless", "settings": outbound_settings, "streamSettings": stream_settings},
				{"tag": "direct", "protocol": "freedom", "settings": {}}
			],
			"routing": {"domainStrategy": "AsIs", "rules": [{"type": "field", "inboundTag": ["socks"], "port": 53, "outboundTag": OUTBOUND_TAG}]}
		}

	async def init_tunnel(self) -> bool:
		"""Фоновый запуск ядра Xray со скачиванием VLESS из GitHub RAW"""
		RAW_URL = "https://githubusercontent.com"
		
		try:
			print("🔄 [СЕТЬ] Скачиваем актуальные VLESS-конфигурации с GitHub...")
			async with aiohttp.ClientSession() as download_session:
				async with download_session.get(RAW_URL, timeout=6) as resp:
					if resp.status == 200:
						text_data = await resp.text()
						lines = [l.strip() for l in text_data.split('\n') if l.strip().startswith("vless://")]
						if lines:
							self.vless_link = lines[0]
							print(f"✅ [СЕТЬ] Получен свежий ключ: {self.vless_link[:50]}...")
		except Exception as e:
			print(f"⚠️ [СЕТЬ] Сбой автообновления ({e}). Используем резервный ключ.")

		if not self.vless_link:
			print("▲ [СЕТЬ] VPN отключен. Скринер работает напрямую.")
			return False

		config_data = self._parse_vless_link()
		if not config_data or not config_data.get("uuid"):
			print("🚨 [СЕТЬ] Ошибка разбора ссылки туннеля.")
			return False

		xray_json = self._build_xray_config(config_data)
		with open(self.config_output_path, "w", encoding="utf-8") as file:
			json.dump(xray_json, file, indent=4, ensure_ascii=False)
			
		try:
			if self.xray_process:
				self.xray_process.terminate()
				await self.xray_process.wait()
				
			self.xray_process = await asyncio.create_subprocess_exec(
				self.xray_bin, "run", "-c", self.config_output_path,
				stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
			)
			print(f"🔒 [СЕТЬ] Локальный ВПН-шлюз успешно поднят на порту {self.socks_port} (PID: {self.xray_process.pid})")
			await asyncio.sleep(3.0)
			return True
		except Exception as e:
			print(f"🚨 [СЕТЬ] Ошибка инициализации ядра Xray: {e}")
			return False

	async def get_session(self) -> aiohttp.ClientSession:
		if self.session and not self.session.closed:
			return self.session
		headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
		if self.vless_link and self.xray_process:
			proxy_url = f"socks5://127.0.0.1:{self.socks_port}"
			connector = ProxyConnector.from_url(proxy_url)
			self.session = aiohttp.ClientSession(connector=connector, headers=headers)
		else:
			self.session = aiohttp.ClientSession(headers=headers)
		return self.session

	async def fetch_json(self, url: str, method: str = "GET", **kwargs) -> dict:
		session = await self.get_session()
		try:
			async with session.request(method, url, timeout=4, **kwargs) as response:
				if response.status == 200:
					return await response.json()
				return None
		except Exception:
			return None

	async def close(self):
		if self.session and not self.session.closed:
			await self.session.close()
		if self.xray_process:
			try:
				self.xray_process.terminate()
				await self.xray_process.wait()
			except Exception:
				pass
