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
			self.tunnel_test_url = str(self.net_config["tunnel_test_url"])
			self.tunnel_probe_timeout = float(self.net_config["tunnel_probe_timeout"])
			self.tunnel_max_attempts = int(self.net_config["tunnel_max_attempts"])
		except KeyError as e:
			raise ValueError(f"🚨 [КОНФИГ] В секции 'network' отсутствует обязательный ключ: {e}")

		self.vless_link = ""
		self.xray_process = None
		self.session = None
		self.tunnel_active = False
		self._initialized = True

	def _parse_vless_link(self, raw_link: str) -> dict:
		"""Безопасный разбор VLESS-ссылки в словарь параметров для Xray."""
		try:
			if not raw_link or not raw_link.startswith("vless://"):
				return {}

			# Разделяем основную ссылку и имя конфигурации после #
			parts = raw_link.split("#")
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

	async def _stop_xray_process(self):
		"""Останавливает текущий процесс Xray перед перезапуском или выходом."""
		if self.xray_process:
			try:
				self.xray_process.terminate()
				await asyncio.wait_for(self.xray_process.wait(), timeout=2.0)
			except Exception:
				try:
					self.xray_process.kill()
				except Exception:
					pass
			finally:
				self.xray_process = None

		if sys.platform != "win32":
			os.system("pkill -f xray 2>/dev/null")

	async def _probe_tunnel_connection(self) -> bool:
		"""Проверяет реальную проходимость трафика через локальный SOCKS5-порт Xray."""
		proxy_url = f"socks5://127.0.0.1:{self.socks_port}"
		timeout = aiohttp.ClientTimeout(total=self.tunnel_probe_timeout)
		try:
			connector = ProxyConnector.from_url(proxy_url)
			async with aiohttp.ClientSession(connector=connector, timeout=timeout) as probe_session:
				async with probe_session.get(self.tunnel_test_url) as resp:
					return resp.status == 200
		except Exception:
			return False



	async def init_tunnel(self) -> bool:
		"""
		Запускает Xray-туннель на Linux VPS и перебирает VLESS-ключи,
		пока не найдет реально рабочий узел.
		"""
		if sys.platform == "win32" and not self.enable_tunnel_on_windows:
			self.tunnel_active = False
			print("🖥️  [СЕТЬ] Работаем на Windows: запуск Xray-туннеля отключен в конфиге, идем напрямую.", flush=True)
			return False

		await self._stop_xray_process()
		await asyncio.sleep(0.3)

		lines = []
		try:
			timeout = aiohttp.ClientTimeout(total=self.http_total_timeout)
			async with aiohttp.ClientSession(timeout=timeout) as download_session:
				async with download_session.get(self.proxies_raw_url) as resp:
					if resp.status == 200:
						text_data = await resp.text()
						lines = [line.strip() for line in text_data.split("\n") if line.strip().startswith("vless://")]
					else:
						logger.error(f"🚨 [СЕТЬ] Не удалось скачать VLESS-список: HTTP {resp.status}")
		except Exception as e:
			logger.error(f"🚨 [СЕТЬ] Ошибка скачивания списка VLESS: {type(e).__name__}: {e}")

		if not lines:
			self.tunnel_active = False
			print("🚨 [СЕТЬ] Список VLESS-ключей пуст или недоступен!", flush=True)
			return False

		random.shuffle(lines)
		candidates = lines[:self.tunnel_max_attempts]
		print(f"🔍 [СЕТЬ] Загружено {len(lines)} ключей. Проверяем до {len(candidates)} кандидатов...", flush=True)

		for attempt, candidate_link in enumerate(candidates, start=1):
			config_data = self._parse_vless_link(candidate_link)
			if not config_data or not config_data.get("uuid"):
				continue

			xray_json = self._build_xray_config(config_data)
			with open(self.config_output_path, "w", encoding="utf-8") as file:
				json.dump(xray_json, file, indent=4, ensure_ascii=False)

			try:
				self.xray_process = await asyncio.create_subprocess_exec(
					self.xray_bin, "run", "-c", self.config_output_path,
					stdout=asyncio.subprocess.DEVNULL,
					stderr=asyncio.subprocess.DEVNULL
				)
				await asyncio.sleep(1.2)

				if self.xray_process.returncode is not None:
					print(f"🚨 [СЕТЬ] Бинарник Xray завершился с кодом {self.xray_process.returncode}. Проверь права chmod +x {self.xray_bin}", flush=True)
					self.tunnel_active = False
					return False

				is_alive = await self._probe_tunnel_connection()
				if is_alive:
					self.vless_link = candidate_link
					self.tunnel_active = True

					if self.session and not self.session.closed:
						await self.session.close()
						self.session = None

					print(f"✅ [СЕТЬ] Живой VLESS-туннель найден с попытки #{attempt}: {config_data['remark']}", flush=True)
					return True

				print(f"⚠️ [СЕТЬ] Ключ #{attempt}/{len(candidates)} не отвечает ({config_data['remark']}), пробуем следующий...", flush=True)
				await self._stop_xray_process()

			except Exception as e:
				logger.error(f"🚨 [СЕТЬ] Ошибка запуска Xray на попытке #{attempt}: {type(e).__name__}: {e}")
				await self._stop_xray_process()

		self.tunnel_active = False
		print(f"🚨 [СЕТЬ] Ни один из {len(candidates)} VLESS-ключей не ответил!", flush=True)
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
			logger.error(f"🚨 [СЕТЬ] Сбой запроса {url}: {type(e).__name__}: {e}")
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
				await self._stop_xray_process()
				self.tunnel_active = False
