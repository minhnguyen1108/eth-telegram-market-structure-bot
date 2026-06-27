from __future__ import annotations

import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.binance_client import Candle
from src.strategy import Pivot, build_signal


def candle(index: int, *, open_price: float, high: float, low: float, close: float, volume: float = 100) -> Candle:
    open_time = datetime(2026, 6, 26, tzinfo=UTC) + timedelta(minutes=15 * index)
    return Candle(
        open_time=open_time,
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=volume,
        close_time=open_time + timedelta(minutes=15) - timedelta(milliseconds=1),
    )


def bearish_setup_candles(*, entry: float, impulse_low: float, swing_high: float, last_high: float | None = None) -> list[Candle]:
    candles = [
        candle(i, open_price=1570, high=1572, low=1568, close=1571, volume=80)
        for i in range(20)
    ]
    candles[-3] = candle(17, open_price=1570, high=swing_high, low=1568, close=1569, volume=90)
    candles[-2] = candle(18, open_price=1568, high=1570, low=1560, close=1567, volume=90)
    candles[-1] = candle(
        19,
        open_price=entry + 1,
        high=last_high if last_high is not None else entry + 1.5,
        low=impulse_low,
        close=entry,
        volume=120,
    )
    return candles


class StrategyQualityFiltersTest(unittest.TestCase):
    def build_bearish_signal(self, *, entry: float, impulse_low: float, swing_high: float):
        lower_tf = bearish_setup_candles(entry=entry, impulse_low=impulse_low, swing_high=swing_high)
        with (
            patch("src.strategy.structure_bias", return_value="bearish"),
            patch(
                "src.strategy.detect_pivots",
                return_value=[
                    Pivot(index=1, price=1600.0, kind="low"),
                    Pivot(index=2, price=impulse_low, kind="low"),
                    Pivot(index=3, price=1570.0, kind="high"),
                    Pivot(index=4, price=swing_high, kind="high"),
                ],
            ),
            patch("src.strategy.bearish_confirmation", return_value=True),
        ):
            return build_signal(
                lower_tf=lower_tf,
                higher_tf=lower_tf,
                risk_reward=2.0,
                min_signal_score=3,
                execution_timeframe="15m",
                higher_timeframe="4h",
                strategy_version="intraday",
            )

    def test_rejects_short_when_close_is_not_in_deep_half_of_value_zone(self) -> None:
        signal = self.build_bearish_signal(entry=1564.08, impulse_low=1545.78, swing_high=1586.5)

        self.assertIsNone(signal)

    def test_rejects_setup_when_stop_distance_is_too_wide(self) -> None:
        signal = self.build_bearish_signal(entry=1570.0, impulse_low=1545.78, swing_high=1586.5)

        self.assertIsNone(signal)

    def test_accepts_deep_pullback_with_tight_risk(self) -> None:
        signal = self.build_bearish_signal(entry=1564.0, impulse_low=1545.0, swing_high=1578.0)

        self.assertIsNotNone(signal)
        self.assertEqual(signal.side, "SHORT")


if __name__ == "__main__":
    unittest.main()
