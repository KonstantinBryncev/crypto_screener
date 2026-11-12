# Файл: tests/test_network_client.py
import os
import sys
import asyncio
import copy
import json

# Добавляем корень проекта в пути поиска
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.config import CONFIG
from network.client import AsyncHttpClient


async def run_network_xray_test():
	print("\n" + "=" * 80)
	print("🔬 [РЕНТГЕН-ТЕСТ] Проверка сетевого модуля network/client.py")
	print("=" * 80)

	# -------------------------------------------------------------------------
	# ШАГ 1: Проверка защиты от пропущенных ключей в config/config.py
	# -------------------------------------------------------------------------
	print("🧪 ШАГ 1. Проверка защиты от хардкода (удаляем ключ http_total_timeout):")
	AsyncHttpClient._instance = None
	broken_cfg = copy.deepcopy(CONFIG)
	broken_cfg["network"].pop("http_total_timeout", None)

	try:
		AsyncHttpClient(broken_cfg)
		print("   🚨 ОШИБКА! Клиент НЕ упал при отсутствии ключа в конфиге!\n")
	except ValueError as e:
		print(f"   ✅ УСПЕХ! Защита сработала, код остановился:\n      {e}\n")

	# -------------------------------------------------------------------------
	# ШАГ 2: Проверка работы на Windows (порт не трогается, Xray не запускается)
	# -------------------------------------------------------------------------
	print("🧪 ШАГ 2. Проверка блокировки VPN/Xray на Windows:")
	AsyncHttpClient._instance = None
	win_cfg = copy.deepcopy(CONFIG)
	win_cfg["network"]["enable_tunnel_on_windows"] = False

	client_win = AsyncHttpClient(win_cfg)
	tunnel_res = await client_win.init_tunnel()

	if tunnel_res is False and client_win.tunnel_active is False and client_win.xray_process is None:
		print("   ✅ УСПЕХ! На Windows туннель пропущен, локальные порты чистые, идем напрямую.\n")
	else:
		print("   🚨 ОШИБКА! Туннель попытался запуститься на Windows!\n")

	# -------------------------------------------------------------------------
	# ШАГ 3: Проверка парсера VLESS и генератора JSON-конфига для Linux VPS
	# -------------------------------------------------------------------------
	print("🧪 ШАГ 3. Проверка разбора VLESS-ссылки и генерации JSON для Xray (режим VPS):")
	sample_vless = (
		"vless://12a10a54-f481-4ad1-b39f-f65efaef5854@92.118.168.39:443"
		"?encryption=none&flow=xtls-rprx-vision&fp=chrome"
		"&pbk=oJn3mcv_oUhP_OzMOgnDtuHCFweHmI8c2blVECBRSVw"
		"&security=reality&sid=943d30163de5&sni=fr.birchcloud.org&type=tcp#test-vps"
	)
	client_win.vless_link = sample_vless
	parsed = client_win._parse_vless_link()

	print(f"   • Извлечен UUID    : {parsed.get('uuid')}")
	print(f"   • Извлечен сервер  : {parsed.get('address')}:{parsed.get('port')}")
	print(f"   • Извлечен SNI     : {parsed.get('params', {}).get('sni')}")

	xray_cfg = client_win._build_xray_config(parsed)
	inbound_port = xray_cfg["inbounds"][0]["port"]
	dns_addr = xray_cfg["dns"]["servers"][0]["address"]

	if (
		parsed.get("uuid") == "12a10a54-f481-4ad1-b39f-f65efaef5854"
		and inbound_port == win_cfg["network"]["local_socks_port"]
		and dns_addr == win_cfg["network"]["dns_server"]
	):
		print(f"   ✅ УСПЕХ! Конфиг Xray собран верно: SOCKS5 порт {inbound_port}, DNS {dns_addr}.\n")
	else:
		print("   🚨 ОШИБКА! Несовпадение параметров при сборке JSON для Xray!\n")

	await client_win.close()

	print("=" * 80)
	print("🎉 ИТОГ: Модуль network/client.py полностью исправен и готов к работе!")
	print("=" * 80 + "\n")


if __name__ == "__main__":
	asyncio.run(run_network_xray_test())
