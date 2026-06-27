from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ai_trade_analyzer import build_trade_analysis_payload, parse_ai_review_output
from src.models import TradeSignal


def closed_trade(trade_id: int, outcome: str, side: str = "SHORT") -> TradeSignal:
    return TradeSignal(
        id=trade_id,
        symbol="ETHUSDT",
        timeframe="15m",
        side=side,
        status="CLOSED",
        bias="bearish" if side == "SHORT" else "bullish",
        strategy_version="intraday",
        signal_time=datetime(2026, 6, 26, 9, 0),
        entry_price=1575.0,
        stop_loss=1585.0,
        take_profit=1555.0,
        risk_reward=2.0,
        signal_score=3,
        reason="market structure pullback",
        setup_json='{"zone_low": 1570, "zone_high": 1580}',
        close_time=datetime(2026, 6, 26, 10, 0),
        close_price=1585.0 if outcome == "LOSS" else 1555.0,
        outcome=outcome,
        pnl_r=-1.0 if outcome == "LOSS" else 2.0,
    )


class AiTradeAnalyzerTest(unittest.TestCase):
    def test_prompt_payload_contains_trade_history_and_no_secret_names(self) -> None:
        payload = build_trade_analysis_payload(
            just_closed=closed_trade(10, "LOSS"),
            history=[closed_trade(1, "WIN"), closed_trade(2, "LOSS"), closed_trade(3, "WIN", side="LONG")],
        )

        payload_text = str(payload)
        self.assertEqual(payload["just_closed_trade"]["id"], 10)
        self.assertEqual(payload["history_stats"]["total_trades"], 3)
        self.assertIn("strategy_rules", payload)
        self.assertIn("group_stats", payload)
        self.assertNotIn("OPENAI_API_KEY", payload_text)
        self.assertNotIn("sk-", payload_text)

    def test_parse_ai_review_output_rejects_invalid_json(self) -> None:
        with self.assertRaisesRegex(ValueError, "valid JSON"):
            parse_ai_review_output("không phải json")

    def test_parse_ai_review_output_rejects_unknown_action(self) -> None:
        with self.assertRaisesRegex(ValueError, "recommended_action"):
            parse_ai_review_output(
                """
                {
                  "summary_vi": "Tóm tắt",
                  "failure_pattern": "Không rõ",
                  "recommended_action": "auto_trade_more",
                  "suggested_rule_change": "Không đổi",
                  "confidence": "low",
                  "risk_note": "Mẫu nhỏ"
                }
                """
            )

    def test_parse_ai_review_output_accepts_valid_schema(self) -> None:
        parsed = parse_ai_review_output(
            """
            {
              "summary_vi": "Lệnh thua do hồi chưa đủ sâu.",
              "failure_pattern": "SHORT ở vùng hồi nông dễ bị quét SL.",
              "recommended_action": "tighten_filter",
              "suggested_rule_change": "Chỉ nhận SHORT khi entry nằm nửa trên của vùng value.",
              "confidence": "medium",
              "risk_note": "Chưa tự áp dụng, cần theo dõi thêm."
            }
            """
        )

        self.assertEqual(parsed["recommended_action"], "tighten_filter")
        self.assertEqual(parsed["confidence"], "medium")


if __name__ == "__main__":
    unittest.main()
