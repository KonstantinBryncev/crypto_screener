import json
import logging
import os
import subprocess
import sys
from urllib.parse import unquote, urlparse, parse_qs

# ==============================================================================
# НАСТРОЙКА КАНАЛОВ ЛОГИРОВАНИЯ (КОНСОЛЬ + ФАЙЛ ЖУРНАЛА)
# ==============================================================================
LOG_FILE_PATH = "vpn_session.log"

logging.basicConfig(
	level=logging.INFO,
	format="%(asctime)s [%(levelname)s] %(message)s",
	datefmt="%Y-%m-%d %H:%M:%S",
	handlers=[
		logging.FileHandler(LOG_FILE_PATH, encoding="utf-8"),
		logging.StreamHandler(sys.stdout)
	]
)

# Путь к конфигурационному файлу приложения
SETTINGS_FILE_PATH = "settings.json"


def load_application_settings(settings_path):
	"""
	Загружает настройки из JSON и проверяет каждую переменную на валидность.
	Выводит лаконичный статус в консоль и полные данные в файл журнала.
	"""
	logging.info(f"=== ШАГ 0: Загрузка конфигурации приложения из {settings_path} ===")
	
	if not os.path.exists(settings_path):
		msg = f"Критическая ошибка: Файл настроек {settings_path} физически отсутствует!"
		logging.error(msg)
		raise FileNotFoundError(msg)

	try:
		with open(settings_path, "r", encoding="utf-8") as file:
			raw_settings = json.load(file)
	except Exception as e:
		msg = f"Критическая ошибка: Файл {settings_path} имеет некорректный формат JSON: {e}"
		logging.error(msg)
		raise ValueError(msg)

	required_keys = ["vless_link", "local_socks_port", "xray_bin_path", "config_output_path"]
	validated_settings = {}
	failed_variables = []

	for key in required_keys:
		try:
			value = raw_settings.get(key)
			if value is None or (isinstance(value, str) and value.strip() == ""):
				raise ValueError("Поле пустое или отсутствует")
				
			if key == "xray_bin_path" and not os.path.exists(os.path.normpath(str(value))):
				raise FileNotFoundError(f"Файл по пути '{value}' не найден на диске")

			validated_settings[key] = value
			print(f"[ИНФО] Проверка переменной {key} => OK")
			
		except Exception as error_reason:
			failed_variables.append((key, str(error_reason)))
			print(f"[ОШИБКА] Проверка переменной {key} => FAIL")

	if failed_variables:
		print("\n[КРИТИЧЕСКИЙ СБОЙ] Запуск невозможен. Некоторые переменные повреждены!")
		for var_name, reason in failed_variables:
			print(f" -> Проблема в '{var_name}': {reason}")
		sys.exit(1)

	print("[УСПЕХ] Конфиг файл успешно загружен и проверен.")
	
	file_logger = logging.getLogger("file_only")
	file_logger.setLevel(logging.INFO)
	if not file_logger.handlers:
		file_handler = logging.FileHandler(LOG_FILE_PATH, encoding="utf-8")
		file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
		file_logger.addHandler(file_handler)
		file_logger.propagate = False

	file_logger.info("--- ДЕТАЛЬНЫЙ ДАМП УСПЕШНО ЗАГРУЖЕННОЙ КОНФИГУРАЦИИ ---")
	for k, v in validated_settings.items():
		file_logger.info(f"Загружено из JSON: {k} = {v}")
	file_logger.info("-------------------------------------------------------")

	return validated_settings


def parse_vless_link(link):
	"""
	Разбирает строку vless:// на отдельные параметры сети и авторизации.
	Гарантированно преобразует списки значений из query-параметров в чистые строки.
	"""
	logging.info("Инициализация парсинга VLESS ссылки...")
	
	parsed = urlparse(link)
	if parsed.scheme != "vless":
		logging.error(f"Схема протокола не верна: {parsed.scheme}")
		raise ValueError("Указанная ссылка не является протоколом VLESS!")

	uuid = parsed.username
	server_address = parsed.hostname
	port = parsed.port

	logging.info(f"Выделен UUID пользователя: {uuid}")
	logging.info(f"Выделен адрес удаленного сервера: {server_address}:{port}")

	logging.info("Чтение параметров сетевого транспорта (Query params)...")
	query_params = parse_qs(parsed.query)

	# КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ: Извлекаем первый элемент списка v[0], чтобы получить строку, а не список
	cleaned_params = {}
	for key, value in query_params.items():
		if value:
			cleaned_params[key] = value[0]
			logging.info(f"-> Параметр сети найден: {key} = {value[0]}")

	remark = unquote(parsed.fragment) if parsed.fragment else "py-3x-connection"
	logging.info(f"Имя профиля из ссылки (Remark): {remark}")

	return {
		"uuid": uuid,
		"address": server_address,
		"port": port,
		"params": cleaned_params,
		"remark": remark
	}


def build_xray_json(parsed_data, local_port):
	"""
	Формирует валидную структуру JSON-конфигурации для ядра Xray-core
	с максимальной защитой от утечек DNS (Anti-DNS Leak).
	"""
	logging.info("Старт сборки защищенной JSON конфигурации для Xray-core...")
	params = parsed_data["params"]

	OUTBOUND_TAG = "proxy"

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

	if params.get("type") == "grpc":
		stream_settings["grpcSettings"] = {
			"serviceName": params.get("serviceName", "")
		}
	elif params.get("type") == "ws":
		stream_settings["wsSettings"] = {
			"path": params.get("path", "/"),
			"headers": {"Host": params.get("sni", "")}
		}

	dns_config = {
		"disableCache": False,
		"disableFallback": True,
		"servers": [
			{
				"address": "https://1.1.1",
				"port": 53,
				"outbound": OUTBOUND_TAG
			}
		]
	}

	full_config = {
		"log": {
			"loglevel": "warning"
		},
		"dns": dns_config,
		"inbounds": [
			{
				"port": local_port,
				"listen": "127.0.0.1",
				"protocol": "socks",
				"settings": {
					"auth": "noauth",
					"udp": True
				},
				"sniffing": {
					"enabled": True,
					"destOverride": ["http", "tls", "quic"],
					"metadataOnly": False
				}
			}
		],
		"outbounds": [
			{
				"tag": OUTBOUND_TAG,
				"protocol": "vless",
				"settings": outbound_settings,
				"streamSettings": stream_settings
			},
			{
				"tag": "direct",
				"protocol": "freedom",
				"settings": {}
			}
		],
		"routing": {
			"domainStrategy": "AsIs",
			"rules": [
				{
					"type": "field",
					"inboundTag": ["socks"],
					"port": 53,
					"outboundTag": OUTBOUND_TAG
				}
			]
		}
	}
	logging.info("Структура JSON с защитой DNS успешно сформирована в памяти.")
	return full_config


def main():
	try:
		settings = load_application_settings(SETTINGS_FILE_PATH)
	except Exception as e:
		logging.error(f"[Сбой] Не удалось инициализировать настройки приложения: {e}")
		return

	vless_link = settings.get("vless_link")
	logging.info(f"Локальный SOCKS5 прокси разворачивается на адресе 127.0.0.1:{local_socks_port}")

	xray_bin_path = os.path.normpath(settings.get("xray_bin_path", "bin/xray.exe"))
	config_output_path = settings.get("config_output_path", "config.json")

	logging.info("=== ШАГ 1: Старт обработки входящей конфигурации ===")
	try:
		config_data = parse_vless_link(vless_link)
		logging.info("[Успешно] Ссылка успешно разобрана на компоненты.")
	except Exception as e:
		logging.error(f"[Сбой] Не удалось разобрать VLESS ссылку: {e}")
		return

	logging.info(f"=== ШАГ 2: Сохранение настроек в файл {config_output_path} ===")
	xray_json = build_xray_json(config_data, local_socks_port)
	
	try:
		with open(config_output_path, "w", encoding="utf-8") as file:
			json.dump(xray_json, file, indent=4, ensure_ascii=False)
		logging.info(f"[Успешно] Структурный JSON записан на диск.")
	except Exception as e:
		logging.error(f"[Сбой] Не удалось сохранить файл конфигурации: {e}")
		return

	logging.info("=== ШАГ 3: Проверка среды исполнения ===")
	if not os.path.exists(xray_bin_path):
		logging.error(f"[Сбой] Критическая ошибка: Файл ядра пропал по пути: {xray_bin_path}")
		return
	logging.info(f"[Успешно] Бинарный файл ядра подтвержден.")

	logging.info(f"=== ШАГ 4: Запуск туннеля ядра Xray ===")
	logging.info(f"Локальный SOCKS5 прокси разворачивается на адресе 127.0.0.1:{local_socks_port}")
	logging.info("Для закрытия ВПН-соединения нажмите комбинацию клавиш [Ctrl + C]")
	
	try:
		# ОТЛАДКА: Убираем перенаправление в никуда, чтобы увидеть реальную ошибку xray.exe на экране
		process = subprocess.Popen([xray_bin_path, "run", "-c", config_output_path])
		logging.info(f"Процесс ядра запущен под системным PID: {process.pid}")
		process.wait()
	except KeyboardInterrupt:
		logging.warning("Перехвачен сигнал прерывания (Ctrl+C). Начинаем процедуру остановки...")
		process.terminate()
		logging.info("[Успешно] Процесс xray.exe принудительно остановлен.")
	except Exception as e:
		logging.error(f"[Сбой] Непредвиденная системная ошибка при работе ядра: {e}")
	finally:
		logging.info("Сессия скрипта py-3x-vpn завершена.")


if __name__ == "__main__":
	logging.info("Запуск управляющей программы...")
	main()
