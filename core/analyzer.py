# Модуль: core/analyzer.py
from collections import deque
from typing import Dict, List

class TickerAnalyzer:
    """
    Модуль математического анализа данных.
    Ищет аномалии цены, всплески объемов и резкие скачки волатильности.
    """

    def __init__(self, 
                 price_change_threshold: float = 1.5, 
                 volume_multiplier: float = 3.0, 
                 volatility_multiplier: float = 4.0,  # Во сколько раз текущее движение должно быть сильнее нормы
                 lookback_period: int = 6):
        """
        :param price_change_threshold: Порог изменения цены в процентах (например, 1.5%)
        :param volume_multiplier: Во сколько раз минутный объем должен превышать средний (например, в 3 раза)
        :param volatility_multiplier: Во сколько раз текущий шаг цены должен превышать средний (например, в 4 раза)
        :param lookback_period: Сколько шагов назад брать для сравнения (6 шагов = 1 минута при опросе раз в 10 сек)
        """
        self.price_threshold: float = price_change_threshold
        self.vol_multiplier: float = volume_multiplier
        self.volatility_multiplier: float = volatility_multiplier
        self.lookback: int = lookback_period

    def analyze(self, history: Dict[str, deque]) -> List[dict]:
        """
        Основной метод анализа всей истории рынка.
        Возвращает список обнаруженных сигналов (PRICE, VOLUME, VOLATILITY).
        """
        signals = []

        for symbol, ticks in history.items():
            # Нам нужно накопить хотя бы двойной lookback период для базовых расчетов
            if len(ticks) <= (self.lookback * 2):
                continue

            # --- ТОЧКИ ДАННЫХ ДЛЯ МАТЕМАТИКИ ---
            t_current = ticks[-1]
            t_minus_1m = ticks[-1 - self.lookback]
            t_minus_2m = ticks[-1 - (self.lookback * 2)]

            current_price = t_current['price']
            old_price = t_minus_1m['price']

            # --- 1. АНАЛИЗ ИЗМЕНЕНИЯ ЦЕНЫ (ПАМП / ДАМП) ---
            if old_price > 0:
                price_delta_pct = ((current_price - old_price) / old_price) * 100
                if abs(price_delta_pct) >= self.price_threshold:
                    direction = "🟢 ПАМП" if price_delta_pct > 0 else "🔴 ДАМП"
                    signals.append({
                        'type': 'PRICE',
                        'symbol': symbol,
                        'direction': direction,
                        'delta': round(price_delta_pct, 2),
                        'main_metric': f"Цена: {current_price}",
                        'volume_info': f"24h Vol: {round(t_current['volume'], 1)}"
                    })

            # --- 2. АНАЛИЗ ВСПЛЕСКА ОБЪЕМА (VOLUME SPIKE) ---
            prev_minute_volume = t_minus_1m['volume'] - t_minus_2m['volume']
            current_minute_volume = t_current['volume'] - t_minus_1m['volume']

            if prev_minute_volume > 0.001 and current_minute_volume > 0.001:
                if current_minute_volume >= (prev_minute_volume * self.vol_multiplier):
                    vol_growth_pct = ((current_minute_volume - prev_minute_volume) / prev_minute_volume) * 100
                    signals.append({
                        'type': 'VOLUME',
                        'symbol': symbol,
                        'direction': "⚡ ВСПЛЕСК ОБЪЕМА",
                        'delta': round(vol_growth_pct, 0),
                        'main_metric': f"Мин. объем: {round(current_minute_volume, 2)} (был: {round(prev_minute_volume, 2)})",
                        'volume_info': f"Рост объема в {round(current_minute_volume / prev_minute_volume, 1)} раз!"
                    })

            # --- 3. АНАЛИЗ РЕЗКОЙ ВОЛАТИЛЬНОСТИ (НОВАЯ МАТЕМАТИКА) ---
            # Вычисляем, насколько цена изменилась за ПОСЛЕДНИЕ 10 СЕКУНД (текущий шаг)
            last_step_price = ticks[-1]['price']
            prev_step_price = ticks[-2]['price']
            
            if prev_step_price > 0:
                current_step_delta = abs(((last_step_price - prev_step_price) / prev_step_price) * 100)
                
                # Считаем среднюю «норму» волатильности монеты за всю историю в нашей памяти (кроме последнего шага)
                total_deltas = 0.0
                count = 0
                
                for i in range(1, len(ticks) - 1):
                    p_old = ticks[i-1]['price']
                    p_new = ticks[i]['price']
                    if p_old > 0:
                        total_deltas += abs(((p_new - p_old) / p_old) * 100)
                        count += 1
                
                if count > 0:
                    average_volatility = total_deltas / count
                    
                    # Защита от абсолютно «мертвых» монет, чтобы не делить на микро-числа
                    if average_volatility > 0.01:
                        # Проверяем: превышает ли текущий 10-секундный рывок среднюю норму в X раз?
                        if current_step_delta >= (average_volatility * self.volatility_multiplier):
                            signals.append({
                                'type': 'VOLATILITY',
                                'symbol': symbol,
                                'direction': "💥 ИМПУЛЬС ВОЛАТИЛЬНОСТИ",
                                'delta': round(current_step_delta, 3),
                                'main_metric': f"Рывок: {round(current_step_delta, 3)}% (Норма: {round(average_volatility, 3)}%)",
                                'volume_info': f"Превышение нормы в {round(current_step_delta / average_volatility, 1)} раз!"
                            })

        return signals
