# Модуль: core/analyzer.py
import logging
import os
import json
from database.storage import DBStorage

logger = logging.getLogger("ArbitrageAnalyzer")

class ArbitrageAnalyzer:
    """
    Математическое ядро скринера-радара.
    Вычисляет расхождения цен и автоматически логирует каждую ситуацию в PostgreSQL.
    """
    def __init__(self):
        self.notifier = None
        self.storage = None
        self._init_database_storage()

    def set_notifier(self, notifier_instance):
        """Метод для динамической привязки модуля уведомлений"""
        self.notifier = notifier_instance

    def _init_database_storage(self):
        """Инициализация модуля базы данных на основе единого файла конфигурации"""
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(current_dir)
            config_path = os.path.join(project_root, "config", "config_bot.json")
            
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    bot_config = json.load(f)
                self.storage = DBStorage(bot_config)
        except Exception as e:
            logger.error(f"Не удалось подключить хранилище СУБД к анализатору: {e}")

    def _get_weighted_average_price(self, orderbook_side: list, target_volume_usdt: float) -> float:
        """Рассчитывает средневзвешенную цену для заданной суммы в USDT."""
        accumulated_usdt = 0.0
        accumulated_crypto = 0.0

        for level in orderbook_side:
            try:
                price = float(level[0])
                amount = float(level[1])
            except (ValueError, IndexError):
                continue

            level_usdt = price * amount

            if accumulated_usdt + level_usdt >= target_volume_usdt:
                needed_usdt = target_volume_usdt - accumulated_usdt
                needed_crypto = needed_usdt / price
                accumulated_crypto += needed_crypto
                accumulated_usdt += needed_usdt
                break
            else:
                accumulated_crypto += amount
                accumulated_usdt += level_usdt

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
        transfer_fee: float,
        base_volume: float,
        min_spread_pct: float,
        trade_fee_pct: float,
        crypto_fees_dict: dict
    ):
        """
        Расчет спреда и логирование в СУБД:
        Порог фильтрации считывается динамически из конфигурационного файла.
        """
        asks_a = orderbook_a.get("asks", [])
        bids_b = orderbook_b.get("bids", [])

        if not asks_a or not bids_b:
            return

        # 1. Покупка на Бирже А
        buy_price_a = self._get_weighted_average_price(asks_a, base_volume)
        if buy_price_a == 0.0:
            return

        crypto_bought = base_volume / buy_price_a
        crypto_after_fee_a = crypto_bought * (1.0 - (trade_fee_pct / 100.0))

        # 2. Продажа на Бирже Б (без учета сетевых издержек вывода)
        crypto_to_sell_b = crypto_after_fee_a
        
        # Вычисляем емкость первого уровня стакана Б для контроля ликвидности
        first_bid_price = float(bids_b[0][0]) if bids_b and bids_b[0] else 0.0
        target_sell_volume_usdt = crypto_to_sell_b * first_bid_price
        
        sell_price_b = self._get_weighted_average_price(bids_b, target_sell_volume_usdt)
        if sell_price_b == 0.0:
            return

        usdt_received = crypto_to_sell_b * sell_price_b
        final_usdt = usdt_received * (1.0 - (trade_fee_pct / 100.0))

        # 3. Подсчет спреда
        net_profit_usdt = final_usdt - base_volume
        net_spread_pct = (net_profit_usdt / base_volume) * 100.0

        # 4. ЗАПИСЬ ВСЕХ ПОЛОЖИТЕЛЬНЫХ СИТУАЦИЙ В POSTGRESQL (Для сбора ТОП-10)
        if net_spread_pct > 0.0 and self.storage:
            try:
                conn = self.storage._get_connection()
                sql = """
                    INSERT INTO possible_trades 
                    (symbol, buy_exchange, sell_exchange, buy_price, sell_price, spread_pct, volume_24h)
                    VALUES (%s, %s, %s, %s, %s, %s, %s);
                """
                with conn.cursor() as cur:
                    cur.execute(sql, (
                        symbol.upper(), 
                        exchange_a_name.lower(), 
                        exchange_b_name.lower(), 
                        float(buy_price_a), 
                        float(sell_price_b), 
                        float(net_spread_pct),
                        float(base_volume)
                    ))
                conn.commit()
                conn.close()
            except Exception as db_err:
                logger.error(f"Ошибка записи арбитражного лога в Postgres: {db_err}")

        # 5. Проверка на триггер (Порог min_spread_pct берется строго из твоего конфига JSON)
        if net_spread_pct >= min_spread_pct:
            signal_text = (
                f"🚨 [РАДАР] Сигнал {symbol}!\n"
                f"📥 Купить [{exchange_a_name.upper()}]: {buy_price_a:.4f}\n"
                f"📤 Продать [{exchange_b_name.upper()}]: {sell_price_b:.4f}\n"
                f"💰 Объем: {base_volume} USDT\n"
                f"📈 Спред (без учета вывода): +{net_profit_usdt:.2f} USDT ({net_spread_pct:.2f}%)"
            )
            
            print("\n" + "="*50)
            print(signal_text)
            print("="*50 + "\n")

            if self.notifier:
                import asyncio
                asyncio.create_task(self.notifier.send_message(signal_text))
