from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.bitget_client import BitgetOrderResult
from src.jobs import execute_bitget_order
from src.models import TradeSignal


class BitgetOrderExecutionTest(unittest.TestCase):
    def test_execute_order_sets_symbol_leverage_before_placing_order(self) -> None:
        signal = TradeSignal(
            id=12,
            symbol="ETHUSDT",
            timeframe="15m",
            side="LONG",
            status="OPEN",
            bias="bullish",
            strategy_version="intraday",
            signal_time=datetime(2026, 6, 26, 12, 0),
            entry_price=1500.0,
            stop_loss=1470.0,
            take_profit=1560.0,
            risk_reward=2.0,
            signal_score=4,
            reason="test",
            setup_json="{}",
        )
        fake_settings = SimpleNamespace(
            bitget_trading_enabled=True,
            bitget_api_key="key",
            bitget_api_secret="secret",
            bitget_api_passphrase="pass",
            bitget_base_url="https://api.bitget.com",
            bitget_product_type="USDT-FUTURES",
            bitget_margin_mode="isolated",
            bitget_margin_coin="USDT",
            bitget_order_size=lambda symbol: "0.01",
            bitget_leverage=lambda symbol: "4",
            bitget_symbol=lambda symbol: symbol,
        )
        client = MagicMock()
        client.place_market_order.return_value = BitgetOrderResult(
            order_id="order-1",
            client_oid="client-1",
            raw_response={"code": "00000"},
        )

        with patch("src.jobs.settings", fake_settings), patch("src.jobs.BitgetClient", return_value=client):
            execute_bitget_order(signal)

        client.set_leverage.assert_called_once_with(
            symbol="ETHUSDT",
            product_type="USDT-FUTURES",
            margin_coin="USDT",
            leverage="4",
        )
        client.place_market_order.assert_called_once()
        self.assertEqual(
            [method_call[0] for method_call in client.method_calls],
            ["set_leverage", "place_market_order"],
        )
        self.assertEqual(signal.bitget_order_status, "PLACED")


if __name__ == "__main__":
    unittest.main()
