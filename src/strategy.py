from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from src.binance_client import Candle


@dataclass(frozen=True)
class Pivot:
    index: int
    price: float
    kind: str


@dataclass(frozen=True)
class SignalSetup:
    side: str
    bias: str
    execution_timeframe: str
    higher_timeframe: str
    signal_score: int
    entry_price: float
    stop_loss: float
    take_profit: float
    reason: str
    risk_reward: float
    structure_low: float
    structure_high: float
    zone_low: float
    zone_high: float
    trigger_candle_time: str
    strategy_version: str = "v1"

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=True)


def ema(values: list[float], period: int) -> float:
    multiplier = 2 / (period + 1)
    current = values[0]
    for value in values[1:]:
        current = (value - current) * multiplier + current
    return current


def detect_pivots(candles: list[Candle], lookback: int = 2) -> list[Pivot]:
    pivots: list[Pivot] = []
    for idx in range(lookback, len(candles) - lookback):
        candle = candles[idx]
        highs = [candles[i].high for i in range(idx - lookback, idx + lookback + 1)]
        lows = [candles[i].low for i in range(idx - lookback, idx + lookback + 1)]
        if candle.high == max(highs):
            pivots.append(Pivot(index=idx, price=candle.high, kind="high"))
        if candle.low == min(lows):
            pivots.append(Pivot(index=idx, price=candle.low, kind="low"))
    return pivots


def structure_bias(candles: list[Candle]) -> str:
    pivots = detect_pivots(candles, lookback=3)
    pivot_highs = [pivot for pivot in pivots if pivot.kind == "high"]
    pivot_lows = [pivot for pivot in pivots if pivot.kind == "low"]
    if len(pivot_highs) < 2 or len(pivot_lows) < 2:
        return "neutral"

    last_highs = pivot_highs[-2:]
    last_lows = pivot_lows[-2:]
    close_values = [candle.close for candle in candles[-60:]]
    ema50 = ema(close_values, min(50, len(close_values)))
    last_close = candles[-1].close

    bullish = last_highs[-1].price > last_highs[-2].price and last_lows[-1].price > last_lows[-2].price and last_close > ema50
    bearish = last_highs[-1].price < last_highs[-2].price and last_lows[-1].price < last_lows[-2].price and last_close < ema50
    if bullish:
        return "bullish"
    if bearish:
        return "bearish"
    return "neutral"


def bullish_confirmation(last_candle: Candle, prev_candle: Candle) -> bool:
    bullish_engulfing = (
        prev_candle.close < prev_candle.open
        and last_candle.close > last_candle.open
        and last_candle.close > prev_candle.open
        and last_candle.open <= prev_candle.close
    )
    pin_bar = (
        last_candle.close > last_candle.open
        and (min(last_candle.close, last_candle.open) - last_candle.low)
        > (last_candle.high - max(last_candle.close, last_candle.open)) * 1.5
    )
    return bullish_engulfing or pin_bar


def bearish_confirmation(last_candle: Candle, prev_candle: Candle) -> bool:
    bearish_engulfing = (
        prev_candle.close > prev_candle.open
        and last_candle.close < last_candle.open
        and last_candle.close < prev_candle.open
        and last_candle.open >= prev_candle.close
    )
    pin_bar = (
        last_candle.close < last_candle.open
        and (last_candle.high - max(last_candle.close, last_candle.open))
        > (min(last_candle.close, last_candle.open) - last_candle.low) * 1.5
    )
    return bearish_engulfing or pin_bar


def build_signal(
    lower_tf: list[Candle],
    higher_tf: list[Candle],
    risk_reward: float,
    min_signal_score: int,
    execution_timeframe: str,
    higher_timeframe: str,
    strategy_version: str,
) -> SignalSetup | None:
    bias = structure_bias(higher_tf)
    if bias == "neutral":
        return None

    pivots = detect_pivots(lower_tf)
    lows = [pivot for pivot in pivots if pivot.kind == "low"]
    highs = [pivot for pivot in pivots if pivot.kind == "high"]
    if len(lows) < 2 or len(highs) < 2:
        return None

    last_candle = lower_tf[-1]
    prev_candle = lower_tf[-2]
    recent_close = last_candle.close
    recent_high = max(candle.high for candle in lower_tf[-12:])
    recent_low = min(candle.low for candle in lower_tf[-12:])

    if bias == "bullish":
        previous_high = highs[-2].price
        swing_low = lows[-1].price
        impulse_high = recent_high
        if impulse_high <= previous_high:
            return None
        range_size = impulse_high - swing_low
        if range_size <= 0:
            return None
        zone_high = impulse_high - range_size * 0.382
        zone_low = impulse_high - range_size * 0.618
        in_zone = zone_low <= recent_close <= zone_high or zone_low <= last_candle.low <= zone_high
        if not in_zone or not bullish_confirmation(last_candle, prev_candle):
            return None
        stop_loss = min(swing_low, last_candle.low) * 0.998
        entry = recent_close
        risk = entry - stop_loss
        if risk <= 0:
            return None
        take_profit = entry + risk * risk_reward
        score = (
            int(impulse_high > previous_high)
            + int(last_candle.volume > prev_candle.volume)
            + int(bullish_confirmation(last_candle, prev_candle))
            + int(recent_low > swing_low * 0.995)
        )
        if score < min_signal_score:
            return None
        return SignalSetup(
            side="LONG",
            bias=bias,
            execution_timeframe=execution_timeframe,
            higher_timeframe=higher_timeframe,
            signal_score=score,
            entry_price=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            reason="Xu hướng khung lớn đang tăng + phá cấu trúc tăng + hồi về vùng giá trị + nến xác nhận tăng.",
            risk_reward=risk_reward,
            structure_low=swing_low,
            structure_high=impulse_high,
            zone_low=zone_low,
            zone_high=zone_high,
            trigger_candle_time=last_candle.close_time.isoformat(),
            strategy_version=strategy_version,
        )

    previous_low = lows[-2].price
    swing_high = highs[-1].price
    impulse_low = recent_low
    if impulse_low >= previous_low:
        return None
    range_size = swing_high - impulse_low
    if range_size <= 0:
        return None
    zone_low = impulse_low + range_size * 0.382
    zone_high = impulse_low + range_size * 0.618
    in_zone = zone_low <= recent_close <= zone_high or zone_low <= last_candle.high <= zone_high
    if not in_zone or not bearish_confirmation(last_candle, prev_candle):
        return None
    stop_loss = max(swing_high, last_candle.high) * 1.002
    entry = recent_close
    risk = stop_loss - entry
    if risk <= 0:
        return None
    take_profit = entry - risk * risk_reward
    score = (
        int(impulse_low < previous_low)
        + int(last_candle.volume > prev_candle.volume)
        + int(bearish_confirmation(last_candle, prev_candle))
        + int(recent_high < swing_high * 1.005)
    )
    if score < min_signal_score:
        return None
    return SignalSetup(
        side="SHORT",
        bias=bias,
        execution_timeframe=execution_timeframe,
        higher_timeframe=higher_timeframe,
        signal_score=score,
        entry_price=entry,
        stop_loss=stop_loss,
        take_profit=take_profit,
        reason="Xu hướng khung lớn đang giảm + phá cấu trúc giảm + hồi về vùng giá trị + nến xác nhận giảm.",
        risk_reward=risk_reward,
        structure_low=impulse_low,
        structure_high=swing_high,
        zone_low=zone_low,
        zone_high=zone_high,
        trigger_candle_time=last_candle.close_time.isoformat(),
        strategy_version=strategy_version,
    )
