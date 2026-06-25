from __future__ import annotations

import unittest
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.models import DailySummary, TradeSignal
from src.storage import daily_summary_from_document, daily_summary_to_document
from src.storage import trade_signal_from_document, trade_signal_to_document


class StorageSerializationTest(unittest.TestCase):
    def test_trade_signal_firestore_round_trip_preserves_core_fields(self) -> None:
        signal = TradeSignal(
            id=42,
            symbol="XAUUSDT",
            timeframe="4h",
            side="LONG",
            status="OPEN",
            bias="bullish",
            strategy_version="swing",
            signal_time=datetime(2026, 6, 25, 16, 0),
            entry_price=2300.25,
            stop_loss=2280.0,
            take_profit=2360.75,
            risk_reward=3.0,
            signal_score=5,
            reason="Break of structure and pullback confirmation.",
            setup_json='{"ok": true}',
            telegram_sent=True,
            bitget_order_status="PLACED",
            bitget_order_id="bitget-123",
        )

        restored = trade_signal_from_document(trade_signal_to_document(signal))

        self.assertEqual(restored.id, 42)
        self.assertEqual(restored.symbol, "XAUUSDT")
        self.assertEqual(restored.timeframe, "4h")
        self.assertEqual(restored.strategy_version, "swing")
        self.assertEqual(restored.signal_time, datetime(2026, 6, 25, 16, 0))
        self.assertEqual(restored.entry_price, 2300.25)
        self.assertIs(restored.telegram_sent, True)
        self.assertEqual(restored.bitget_order_status, "PLACED")
        self.assertEqual(restored.bitget_order_id, "bitget-123")

    def test_daily_summary_firestore_round_trip_uses_iso_date_key(self) -> None:
        summary = DailySummary(
            id=7,
            summary_date=date(2026, 6, 25),
            total_trades=4,
            wins=3,
            losses=1,
            winrate=75.0,
            total_r=5.0,
            notes="Daily summary.",
            created_at=datetime(2026, 6, 26, 0, 5),
        )

        document = daily_summary_to_document(summary)
        restored = daily_summary_from_document(document)

        self.assertEqual(document["summary_date"], "2026-06-25")
        self.assertEqual(restored.summary_date, date(2026, 6, 25))
        self.assertEqual(restored.total_trades, 4)
        self.assertEqual(restored.winrate, 75.0)
        self.assertEqual(restored.created_at, datetime(2026, 6, 26, 0, 5))


if __name__ == "__main__":
    unittest.main()
