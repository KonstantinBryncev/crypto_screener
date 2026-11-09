# Файл: core/analyzer.py
import logging

logger = logging.getLogger("ArbitrageAnalyzer")

class ArbitrageAnalyzer:
    """
    Модуль математического анализа межбиржевого спреда.
    Рассчитывает чистую прибыль с учетом биржевых комиссий и фильтрует мусор.
    """
    def __init__(self):
        self.notifier = None

    def set_notifier(self, notifier):
        """Установка нотификатора для отправки сигналов в Телеграм"""
        self.notifier = notifier

    def calculate_spot_spread(
        self,
        symbol: str,
        exchange_a_name: str,
        orderbook_a: dict,
        exchange_b_name: str,
        orderbook_b: dict,
        base_volume: float = 500.0,
        min_spread_pct: float = 0.5,  # Наш боевой фильтр, например 0.5%
        max_spread_pct: float = 15.0,
        trade_fee_pct: float = 0.1
    ):
        """
        Рассчитывает спред между покупкой на Бирже А (по Ask) и продажей на Бирже Б (по Bid).
        Выводит логи В Консоль СТРОГО если спред превышает установленный min_spread_pct.
        """
        try:
            asks_a = orderbook_a.get("asks", [])
            bids_b = orderbook_b.get("bids", [])

            if not asks_a or not bids_b:
                return

            # Берем лучшие цены из стаканов
            best_ask_a = float(asks_a[0][0])
            best_bid_b = float(bids_b[0][0])

            if best_ask_a <= 0:
                return

            # Считаем грязный спред в процентах
            raw_spread_pct = ((best_bid_b - best_ask_a) / best_ask_a) * 100.0
            
            # Считаем чистый спред за вычетом комиссий на обеих биржах (вход + выход)
            total_fees_pct = trade_fee_pct * 2.0
            net_spread_pct = raw_spread_pct - total_fees_pct

            # Защитный фильтр от нереального спама (закрытые кошельки, баги стаканов)
            if net_spread_pct > max_spread_pct:
                return

            # =========================================================================
            # 🎯 ЖЕСТКИЙ БОЕВОЙ ФИЛЬТР КОНСОЛИ И ТЕЛЕГРАМА
            # =========================================================================
            # Выводим информацию ТОЛЬКО если чистый профит выше твоего порога (например, 0.5%)
            if net_spread_pct >= min_spread_pct:
                
                # Считаем чистый профит в USDT от объема сделки
                profit_usdt = (base_volume * (net_spread_pct / 100.0))
                
                # Красивый, чистый консольный вывод без мусора
                print(f"🔥 [СИГНАЛ] Найдена связка {symbol}!")
                print(f"🛒 Купить [{exchange_a_name.upper()}]: {best_ask_a:.6f}")
                print(f"💰 Продать [{exchange_b_name.upper()}]: {best_bid_b:.6f}")
                print(f"📈 Чистый спред: +{net_spread_pct:.2f}% (+{profit_usdt:.2f} USDT)\n", flush=True)

                # Отправляем сочный сигнал в Телеграм на телефон
                if self.notifier:
                    msg = (
                        f"🚨 *АРБИТРАЖНЫЙ СИГНАЛ!*\n\n"
                        f"💱 *Пара:* `{symbol}`\n"
                        f"🟢 *Купить ({exchange_a_name.upper()}):* `{best_ask_a:.6f}`\n"
                        f"🔴 *Продать ({exchange_b_name.upper()}):* `{best_bid_b:.6f}`\n\n"
                        f"📊 *Чистый спред:* `+{net_spread_pct:.2f}%` \n"
                        f"💵 *Профит с {base_volume}$:* `+{profit_usdt:.2f} USDT`"
                    )
                    # Асинхронно пуляем в Телеграм
                    import asyncio
                    asyncio.create_task(self.notifier.send_message(msg))

        except Exception as e:
            logger.error(f"Ошибка в математике анализатора спреда: {e}")
