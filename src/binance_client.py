from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import requests


BINANCE_API_URL = "https://api.binance.com/api/v3/klines"


@dataclass(frozen=True)
class Candle:
    open_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    close_time: datetime


def fetch_klines(symbol: str, interval: str, limit: int = 300) -> list[Candle]:
    response = requests.get(
        BINANCE_API_URL,
        params={"symbol": symbol, "interval": interval, "limit": limit},
        timeout=30,
    )
    response.raise_for_status()
    candles = []
    for row in response.json():
        candles.append(
            Candle(
                open_time=datetime.fromtimestamp(row[0] / 1000, tz=UTC),
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=float(row[5]),
                close_time=datetime.fromtimestamp(row[6] / 1000, tz=UTC),
            )
        )
    return candles
