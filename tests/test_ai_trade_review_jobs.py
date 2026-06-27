from __future__ import annotations

import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.binance_client import Candle
from src.jobs import maybe_send_ai_trade_reviews, run_trade_evaluation
from src.models import AiTradeReview, TradeSignal


def closed_trade(trade_id: int, outcome: str = "LOSS") -> TradeSignal:
    return TradeSignal(
        id=trade_id,
        symbol="ETHUSDT",
        timeframe="15m",
        side="SHORT",
        status="CLOSED",
        bias="bearish",
        strategy_version="intraday",
        signal_time=datetime(2026, 6, 26, 9, 0),
        entry_price=1575.0,
        stop_loss=1585.0,
        take_profit=1555.0,
        risk_reward=2.0,
        signal_score=3,
        reason="market structure pullback",
        setup_json="{}",
        close_time=datetime(2026, 6, 26, 10, 0),
        close_price=1585.0 if outcome == "LOSS" else 1555.0,
        outcome=outcome,
        pnl_r=-1.0 if outcome == "LOSS" else 2.0,
    )


def open_trade() -> TradeSignal:
    return TradeSignal(
        id=99,
        symbol="ETHUSDT",
        timeframe="15m",
        side="LONG",
        status="OPEN",
        bias="bullish",
        strategy_version="intraday",
        signal_time=datetime(2026, 6, 26, 9, 0),
        entry_price=100.0,
        stop_loss=95.0,
        take_profit=110.0,
        risk_reward=2.0,
        signal_score=4,
        reason="test",
        setup_json="{}",
    )


def ai_review(trade_id: int) -> AiTradeReview:
    return AiTradeReview(
        trade_signal_id=trade_id,
        generated_at=datetime(2026, 6, 26, 10, 5),
        symbol="ETHUSDT",
        timeframe="15m",
        strategy_version="intraday",
        outcome="LOSS",
        summary_vi="Lệnh vừa đóng đã được AI phân tích.",
        failure_pattern="Chưa có mẫu lỗi lặp lại rõ ràng.",
        recommended_action="needs_more_data",
        suggested_rule_change="Chưa đổi rule, tiếp tục thu thập dữ liệu.",
        confidence="low",
        risk_note="AI chỉ đề xuất, chưa tự áp dụng.",
        raw_response="{}",
    )


class FakeStorage:
    def __init__(self, open_trades: list[TradeSignal], closed_trades: list[TradeSignal]) -> None:
        self.open_trades = open_trades
        self.closed_trades = closed_trades
        self.updated: list[TradeSignal] = []
        self.strategy_insights = []
        self.ai_reviews = []

    def list_open_trades(self) -> list[TradeSignal]:
        return self.open_trades

    def list_closed_trades(self) -> list[TradeSignal]:
        return self.closed_trades

    def update_trade_signal(self, signal: TradeSignal) -> TradeSignal:
        self.updated.append(signal)
        if signal.status == "CLOSED" and signal not in self.closed_trades:
            self.closed_trades.append(signal)
        return signal

    def upsert_strategy_insight(self, insight):
        self.strategy_insights.append(insight)
        return insight

    def upsert_ai_trade_review(self, review: AiTradeReview) -> AiTradeReview:
        self.ai_reviews.append(review)
        return review


class AiTradeReviewJobsTest(unittest.TestCase):
    def test_maybe_send_ai_trade_reviews_runs_when_enabled_and_trade_closed(self) -> None:
        trade = closed_trade(10)
        storage = FakeStorage([], [closed_trade(1), closed_trade(2), closed_trade(3), trade])
        fake_settings = SimpleNamespace(
            ai_trade_analysis_enabled=True,
            openai_api_key="configured",
            ai_min_closed_trades=2,
            ai_analysis_lookback=30,
            telegram_bot_token="token",
            telegram_chat_id="chat",
        )
        analyzer = MagicMock(return_value=ai_review(trade.id))
        sender = MagicMock()

        with patch("src.jobs.settings", fake_settings):
            reviews = maybe_send_ai_trade_reviews(storage, [trade], storage.closed_trades, analyzer=analyzer, sender=sender)

        self.assertEqual(len(reviews), 1)
        analyzer.assert_called_once()
        sender.assert_called_once()
        self.assertEqual(storage.ai_reviews[0].trade_signal_id, trade.id)

    def test_maybe_send_ai_trade_reviews_does_nothing_when_disabled(self) -> None:
        trade = closed_trade(10)
        storage = FakeStorage([], [closed_trade(1), trade])
        fake_settings = SimpleNamespace(
            ai_trade_analysis_enabled=False,
            openai_api_key="configured",
            ai_min_closed_trades=1,
            ai_analysis_lookback=30,
            telegram_bot_token="token",
            telegram_chat_id="chat",
        )
        analyzer = MagicMock(return_value=ai_review(trade.id))

        with patch("src.jobs.settings", fake_settings):
            reviews = maybe_send_ai_trade_reviews(storage, [trade], storage.closed_trades, analyzer=analyzer)

        self.assertEqual(reviews, [])
        analyzer.assert_not_called()
        self.assertEqual(storage.ai_reviews, [])

    def test_run_trade_evaluation_keeps_normal_report_when_ai_fails(self) -> None:
        trade = open_trade()
        storage = FakeStorage([trade], [])
        fake_settings = SimpleNamespace(
            telegram_bot_token="token",
            telegram_chat_id="chat",
            min_signal_score=3,
            swing_min_signal_score=3,
            winrate_alert_threshold=45,
        )
        candles = [
            Candle(
                open_time=datetime(2026, 6, 26, 2, 15, tzinfo=UTC),
                open=100.0,
                high=111.0,
                low=99.0,
                close=110.0,
                volume=1.0,
                close_time=datetime(2026, 6, 26, 2, 29, tzinfo=UTC),
            )
        ]

        with (
            patch("src.jobs.init_storage", return_value=storage),
            patch("src.jobs.fetch_klines", return_value=candles),
            patch("src.jobs.settings", fake_settings),
            patch("src.jobs.send_telegram_message") as sender,
            patch("src.jobs.maybe_send_ai_trade_reviews", side_effect=RuntimeError("OpenAI down")) as ai_hook,
        ):
            result = run_trade_evaluation()

        self.assertIn("Closed now: 1", result)
        self.assertEqual(trade.status, "CLOSED")
        self.assertEqual(trade.outcome, "WIN")
        sender.assert_called_once()
        ai_hook.assert_called_once()


if __name__ == "__main__":
    unittest.main()
