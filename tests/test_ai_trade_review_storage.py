from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.models import AiTradeReview
from src.storage import ai_trade_review_from_document, ai_trade_review_to_document


class AiTradeReviewStorageTest(unittest.TestCase):
    def test_ai_trade_review_firestore_round_trip_preserves_fields(self) -> None:
        review = AiTradeReview(
            id=7,
            trade_signal_id=42,
            generated_at=datetime(2026, 6, 26, 17, 30),
            symbol="ETHUSDT",
            timeframe="15m",
            strategy_version="intraday",
            outcome="LOSS",
            summary_vi="Lệnh thua do hồi chưa đủ sâu.",
            failure_pattern="SHORT ở vùng hồi nông dễ bị quét SL.",
            recommended_action="tighten_filter",
            suggested_rule_change="Chỉ nhận SHORT khi entry nằm nửa trên vùng value.",
            confidence="medium",
            risk_note="Mẫu còn nhỏ, chưa tự áp dụng vào live.",
            raw_response='{"recommended_action":"tighten_filter"}',
        )

        document = ai_trade_review_to_document(review)
        restored = ai_trade_review_from_document(document)

        self.assertEqual(document["trade_signal_id"], 42)
        self.assertEqual(restored.id, 7)
        self.assertEqual(restored.trade_signal_id, 42)
        self.assertEqual(restored.symbol, "ETHUSDT")
        self.assertEqual(restored.timeframe, "15m")
        self.assertEqual(restored.strategy_version, "intraday")
        self.assertEqual(restored.outcome, "LOSS")
        self.assertEqual(restored.recommended_action, "tighten_filter")
        self.assertEqual(restored.confidence, "medium")
        self.assertEqual(restored.generated_at, datetime(2026, 6, 26, 17, 30))


if __name__ == "__main__":
    unittest.main()
