# Файл: core/analyzer.py
import logging
import psycopg2
from datetime import datetime

logger = logging.getLogger("ArbitrageAnalyzer")

class ArbitrageAnalyzer:
    """
    Модуль математического анализа межбиржевого спреда.
    Рассчитывает чистую прибыль с учетом комиссий и сохраняет сигналы в PostgreSQL.
    """
    def __init__(self):
        self.notifier = None
        # Строка подключения к твоей базе данных (берем доступы из конфига сервера)
        self.db_dsn = "dbname=crypto_db user=postgres password=CryptoDB_2026_Secure host=127.0.0.1 port=5432"

    def set_notifier(self, notifier):
        """Установка нотификатора для отправки сигналов в Телеграм"""
        self.notifier = notifier

    def _save_to_database(self, symbol: str, ex_buy: str, ex_sell: str, buy_price: float, sell_price: float, spread: float):
        """Внутренний метод жесткой записи сигнала в таблицу possible_trades"""
        query = """
            INSERT INTO possible_trades (timestamp, symbol, buy_exchange, sell_exchange, buy_price, sell_price, net_spread)
            VALUES (%s, %s, %s, %s, %s, %s, %s);
        """
        conn = None
        try:
            conn = psycopg2.connect(self.db_dsn)
            with conn.cursor() as cur:
                # 🎯 Записываем строго под структуру DBeaver: timestamp на текущий момент
                cur.execute(query, (
                    datetime.now(),
                    symbol,
                    ex_buy.upper(),
                    ex_sell.upper(),
                    buy_price,
                    sell_price,
                    round(spread, 2)
                ))
            conn.commit()
        except Exception as db_err:
            # Если база ругнется на типы данных — мы сразу увидим это в bot.log
            print(f"⚠️ [БАЗА ДАННЫХ ОШИБКА] Не удалось сохранить связку: {db_err}", flush=True)
        finally:
            if conn:
                conn.close()

    def calculate_spot_spread(
        self,
        symbol: str,
        exchange_a_name: str,
        orderbook_a: dict,
        exchange_b_name: str,
        orderbook_b: dict,
        base_volume: float = 500.0,
        min_spread_pct: float = 0.5,
        max_spread_pct: float = 15.0,
        trade_fee_pct: float = 0.1
    ):
        """Рассчитывает спред и отправляет данные в консоль, базу и Телеграм"""
        try:
            asks_a = orderbook_a.get("asks", [])
            bids_b = orderbook_b.get("bids", [])

            if not asks_a or not bids_b:
                return

            best_ask_a = float(asks_a[0][0])
            best_bid_b = float(bids_b[0][0])

            if best_ask_a <= 0:
                return

            raw_spread_pct = ((best_bid_b - best_ask_a) / best_ask_a) * 100.0
            total_fees_pct = trade_fee_pct * 2.0
            net_spread_pct = raw_spread_pct - total_fees_pct

            if net_spread_pct > max_spread_pct:
                return

            # 🎯 БОЕВОЙ ФИЛЬТР ОТ +0.5%
            if net_spread_pct >= min_spread_pct:
                profit_usdt = (base_volume * (net_spread_pct / 100.0))
                
                # 1. Вывод в консоль
                print(f"🔥 [СИГНАЛ] Найдена связка {symbol}!")
                print(f"🛒 Купить [{exchange_a_name.upper()}]: {best_ask_a:.6f}")
                print(f"💰 Продать [{exchange_b_name.upper()}]: {best_bid_b:.6f}")
                print(f"📈 Чистый спред: +{net_spread_pct:.2f}% (+{profit_usdt:.2f} USDT)\n", flush=True)

                # 2. ЖЕСТКАЯ ЗАПИСЬ В POSTGRESQL
                self._save_to_database(
                    symbol=symbol,
                    ex_buy=exchange_a_name,
                    ex_sell=exchange_b_name,
                    buy_price=best_ask_a,
                    sell_price=best_bid_b,
                    spread=net_spread_pct
                )

                # 3. Отправка в Телеграм
                if self.notifier:
                    msg = (
                        f"🚨 *АРБИТРАЖНЫЙ СИГНАЛ!*\n\n"
                        f"💱 *Пара:* `{symbol}`\n"
                        f"🟢 *Купить ({exchange_a_name.upper()}):* `{best_ask_a:.6f}`\n"
                        f"🔴 *Продать ({exchange_b_name.upper()}):* `{best_bid_b:.6f}`\n\n"
                        f"📊 *Чистый спред:* `+{net_spread_pct:.2f}%` \n"
                        f"💵 *Профит с {base_volume}$:* `+{profit_usdt:.2f} USDT`"
                    )
                    import asyncio
                    asyncio.create_task(self.notifier.send_message(msg))

        except Exception as e:
            logger.error(f"Ошибка в математике анализатора спреда: {e}")
