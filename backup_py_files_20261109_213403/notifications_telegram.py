import asyncio
import logging


logger = logging.getLogger("TelegramNotifier")

class TelegramNotifier:
	"""
	Модуль для асинхронной отправки арбитражных сигналов и системных событий в Telegram.
	Автоматически использует общий туннель Xray, развернутый в HttpClient.
	"""
	def __init__(self, bot_token: str, chat_id: str, network_client):
		self.bot_token = str(bot_token).strip()
		self.chat_id = str(chat_id).strip()
		self.network_client = network_client # Передаем ссылку на наш AsyncHttpClient

	async def send_message(self, text: str) -> bool:
		"""
		Отправляет текстовое сообщение в Telegram через центральный защищенный клиент.
		"""
		if not self.bot_token or "ТВОЙ_" in self.bot_token or not self.chat_id:
			return False

		url = f"https://api/telegram.org{self.bot_token}/sendMessage"
		
		payload = {
			"chat_id": self.chat_id,
			"text": str(text),
			"parse_mode": "Markdown"
		}

		# Перенаправляем отправку в fetch_json нашего клиента, который сам применит VLESS-туннель
		response = await self.network_client.fetch_json(
			url=url,
			method="POST",
			headers={"Content-Type": "application/json"},
			data=json.dumps(payload)
		)
		
		return response is not None