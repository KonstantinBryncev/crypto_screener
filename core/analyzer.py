class ArbitrageAnalyzer:
	"""
	Математическое ядро скринера. Отвечает за парсинг стаканов цен,
	вычисление чистых межбиржевых спредов с учетом всех комиссий
	и вывод результатов в консоль и Telegram.
	"""
	def __init__(self):
		# Ссылка на объект нотификатора Telegram (заполняется динамически из менеджера)
		self.notifier = None

	def set_notifier(self, notifier_instance):
		"""Метод для динамической привязки модуля уведомлений"""
		self.notifier = notifier_instance

# Модуль: core/analyzer.py
import logging

logger = logging.getLogger("ArbitrageAnalyzer")

class ArbitrageAnalyzer:
    """
    Математическое ядро скринера. Отвечает за парсинг стаканов цен,
    вычисление чистых межбиржевых спредов с учетом всех комиссий
    и вывод результатов в консоль и Telegram.
    """
    def __init__(self):
        self.notifier = None

    def set_notifier(self, notifier_instance):
        """Метод для динамической привязки модуля уведомлений"""
        self.notifier = notifier_instance

    def _get_weighted_average_price(self, orderbook_side: list, target_volume_usdt: float) -> float:
        """
        Рассчитывает средневзвешенную цену для заданной суммы в USDT.
        Идет вглубь стакана, чтобы гарантировать исполнение всего объема ордера.
        orderbook_side: список уровней [[price, amount], [price, amount], ...]
        """
        accumulated_usdt = 0.0
        accumulated_crypto = 0.0

        for level in orderbook_side:
            try:
                price = float(level[0])
                amount = float(level[1])
            except (ValueError, IndexError):
                continue

            level_usdt = price * amount

            # Если текущего уровня хватает, чтобы закрыть остаток объема
            if accumulated_usdt + level_usdt >= target_volume_usdt:
                needed_usdt = target_volume_usdt - accumulated_usdt
                needed_crypto = needed_usdt / price
                accumulated_crypto += needed_crypto
                accumulated_usdt += needed_usdt
                break
            else:
                # Забираем уровень полностью
                accumulated_crypto += amount
                accumulated_usdt += level_usdt

        # Если глубины стакана не хватило под наш объем
        if accumulated_usdt < target_volume_usdt or accumulated_crypto == 0:
            return 0.0

        return accumulated_usdt / accumulated_crypto

    def calculate_spot_spread(
        self,
        symbol: str,
        exchange_a_name: str,
        orderbook_a: dict,
        exchange_b_name: str,
        orderbook_b: dict,
        transfer_fee_crypto: float,
        base_volume_usdt: float,
        min_spread_pct: float,
        trade_fee_pct: float
    ):
        """
        Полный расчет межбиржевого спреда:
        1. Считает реальную цену покупки на бирже А (по стакану asks)
        2. Считает реальную цену продажи на бирже Б (по стакану bids)
        3. Вычитает торговые комиссии (туда-обратно)
        4. Вычитает фиксу за перевод между биржами в крипте
        5. Сравнивает чистый профит с минимальным порогом
        """
        # Извлекаем стороны стаканов (asks для покупки, bids для продажи)
        asks_a = orderbook_a.get("asks", [])
        bids_b = orderbook_b.get("bids", [])

        if not asks_a or not bids_b:
            return

        # Шаг 1: Считаем среднюю цену покупки на Бирже А с учетом объема
        buy_price_a = self._get_weighted_average_price(asks_a, base_volume_usdt)
        if buy_price_a == 0.0:
            return  # Ликвидности стакана А не хватает на объем ордера

        # Сколько крипты мы грязными купим на Бирже А
        crypto_bought = base_volume_usdt / buy_price_a
        
        # Минусуем комиссию за торговую сделку на Бирже А
        crypto_after_fee_a = crypto_bought * (1.0 - (trade_fee_pct / 100.0))

        # Шаг 2: Перевод между биржами (вычитаем фиксированную комиссию сети)
        crypto_to_sell_b = crypto_after_fee_a - transfer_fee_crypto
        if crypto_to_sell_b <= 0:
            return  # Комиссия сети сожрала всю покупку

        # Шаг 3: Считаем среднюю цену продажи на Бирже Б с учетом объема
        # Считаем емкость стакана на Бирже Б под наш остаток крипты
        target_sell_volume_usdt = crypto_to_sell_b * float(bids_b[0][0] if bids_b else 0)
        sell_price_b = self._get_weighted_average_price(bids_b, target_sell_volume_usdt)
        if sell_price_b == 0.0:
            return

        # Сколько USDT получаем грязными после продажи на Бирже Б
        usdt_received = crypto_to_sell_b * sell_price_b
        
        # Минусуем комиссию за торговую сделку на Бирже Б
        final_usdt = usdt_received * (1.0 - (trade_fee_pct / 100.0))

        # Шаг 4: Считаем чистый профит в USDT и в процентах
        net_profit_usdt = final_usdt - base_volume_usdt
        net_spread_pct = (net_profit_usdt / base_volume_usdt) * 100.0

        # Шаг 5: Проверка на триггер (если профит выше минимального порога из конфига)
        if net_spread_pct >= min_spread_pct:
            signal_text = (
                f"🚨 [СИГНАЛ] Найдена связка {symbol}!\n"
                f"📥 Покупка [{exchange_a_name.upper()}]: {buy_price_a:.4f}\n"
                f"📤 Продажа [{exchange_b_name.upper()}]: {sell_price_b:.4f}\n"
                f"💰 Объем ордера: {base_volume_usdt} USDT\n"
                f"⛽ Комиссия сети: {transfer_fee_crypto} {symbol.split('/')[0]}\n"
                f"📈 Чистый профит: +{net_profit_usdt:.2f} USDT ({net_spread_pct:.2f}%)"
            )
            
            # Выводим в красивом блоке в консоль
            print("\n" + "="*50)
            print(signal_text)
            print("="*50 + "\n")

            # Если Telegram-клиент привязан, пуляем уведомление на телефон
            if self.notifier:
                import asyncio
                asyncio.create_task(self.notifier.send_message(signal_text))
