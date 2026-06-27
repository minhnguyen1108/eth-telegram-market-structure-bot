from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime
from typing import Any

from src.config import settings
from src.models import AiTradeReview, TradeSignal
from src.strategy import MAX_SETUP_RISK_PERCENT
from src.time_utils import local_now_naive


ALLOWED_ACTIONS = {"keep_strategy", "tighten_filter", "loosen_filter", "disable_setup", "needs_more_data"}
ALLOWED_CONFIDENCE = {"low", "medium", "high"}
REQUIRED_REVIEW_FIELDS = {
    "summary_vi",
    "failure_pattern",
    "recommended_action",
    "suggested_rule_change",
    "confidence",
    "risk_note",
}

AI_REVIEW_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary_vi": {"type": "string"},
        "failure_pattern": {"type": "string"},
        "recommended_action": {
            "type": "string",
            "enum": sorted(ALLOWED_ACTIONS),
        },
        "suggested_rule_change": {"type": "string"},
        "confidence": {
            "type": "string",
            "enum": sorted(ALLOWED_CONFIDENCE),
        },
        "risk_note": {"type": "string"},
    },
    "required": sorted(REQUIRED_REVIEW_FIELDS),
    "additionalProperties": False,
}


def safe_iso(value: datetime | None) -> str | None:
    return value.isoformat(sep=" ", timespec="minutes") if value else None


def parse_setup_json(setup_json: str | None) -> dict[str, Any]:
    if not setup_json:
        return {}
    try:
        parsed = json.loads(setup_json)
    except json.JSONDecodeError:
        return {"raw": setup_json[:500]}
    return parsed if isinstance(parsed, dict) else {"raw": parsed}


def trade_to_payload(trade: TradeSignal) -> dict[str, Any]:
    return {
        "id": trade.id,
        "symbol": trade.symbol,
        "timeframe": trade.timeframe,
        "side": trade.side,
        "status": trade.status,
        "bias": trade.bias,
        "strategy_version": trade.strategy_version,
        "signal_time": safe_iso(trade.signal_time),
        "close_time": safe_iso(trade.close_time),
        "entry_price": trade.entry_price,
        "stop_loss": trade.stop_loss,
        "take_profit": trade.take_profit,
        "close_price": trade.close_price,
        "outcome": trade.outcome,
        "pnl_r": trade.pnl_r,
        "risk_reward": trade.risk_reward,
        "signal_score": trade.signal_score,
        "reason": trade.reason,
        "setup": parse_setup_json(trade.setup_json),
    }


def winrate_percent(wins: int, total: int) -> float:
    return round((wins / total) * 100, 2) if total else 0.0


def build_group_stats(history: list[TradeSignal]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str], list[TradeSignal]] = defaultdict(list)
    for trade in history:
        grouped[(trade.symbol, trade.timeframe, trade.strategy_version, trade.side)].append(trade)

    stats = []
    for (symbol, timeframe, strategy_version, side), trades in sorted(grouped.items()):
        wins = sum(1 for trade in trades if trade.outcome == "WIN")
        losses = sum(1 for trade in trades if trade.outcome == "LOSS")
        stats.append(
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "strategy_version": strategy_version,
                "side": side,
                "total_trades": len(trades),
                "wins": wins,
                "losses": losses,
                "winrate": winrate_percent(wins, len(trades)),
                "total_r": round(sum(trade.pnl_r or 0 for trade in trades), 2),
            }
        )
    return stats


def build_trade_analysis_payload(just_closed: TradeSignal, history: list[TradeSignal]) -> dict[str, Any]:
    wins = sum(1 for trade in history if trade.outcome == "WIN")
    losses = sum(1 for trade in history if trade.outcome == "LOSS")
    return {
        "task": "Phân tích lệnh đã đóng theo vai trò cố vấn. Không tự đặt lệnh, không tự sửa code, không tự đổi chiến lược live.",
        "just_closed_trade": trade_to_payload(just_closed),
        "recent_closed_trades": [trade_to_payload(trade) for trade in history],
        "history_stats": {
            "total_trades": len(history),
            "wins": wins,
            "losses": losses,
            "winrate": winrate_percent(wins, len(history)),
            "total_r": round(sum(trade.pnl_r or 0 for trade in history), 2),
        },
        "group_stats": build_group_stats(history),
        "strategy_rules": {
            "max_setup_risk_percent": MAX_SETUP_RISK_PERCENT,
            "deep_pullback_filter": "LONG chỉ nhận entry ở nửa dưới vùng value; SHORT chỉ nhận entry ở nửa trên vùng value.",
            "weekend_filter": "Không mở lệnh vào Thứ 7 / Chủ nhật theo giờ Asia/Bangkok.",
            "max_open_trades_per_timeframe": settings.max_open_trades_per_timeframe,
            "advisory_only": True,
        },
        "output_schema": {
            "summary_vi": "Tóm tắt ngắn bằng tiếng Việt có dấu.",
            "failure_pattern": "Mẫu lỗi lặp lại nếu có.",
            "recommended_action": sorted(ALLOWED_ACTIONS),
            "suggested_rule_change": "Đề xuất rule cụ thể ở dạng text, không tự áp dụng.",
            "confidence": sorted(ALLOWED_CONFIDENCE),
            "risk_note": "Ghi chú sample size và rủi ro khi chạy live.",
        },
    }


def strip_code_fences(output_text: str) -> str:
    text = output_text.strip()
    fence_match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    return fence_match.group(1).strip() if fence_match else text


def parse_ai_review_output(output_text: str) -> dict[str, str]:
    try:
        parsed = json.loads(strip_code_fences(output_text))
    except json.JSONDecodeError as exc:
        raise ValueError("AI output must be valid JSON.") from exc

    if not isinstance(parsed, dict):
        raise ValueError("AI output must be a JSON object.")

    missing = REQUIRED_REVIEW_FIELDS - set(parsed)
    if missing:
        raise ValueError(f"AI output missing fields: {', '.join(sorted(missing))}.")

    normalized = {field: str(parsed[field]).strip() for field in REQUIRED_REVIEW_FIELDS}
    if normalized["recommended_action"] not in ALLOWED_ACTIONS:
        raise ValueError("AI output recommended_action is not allowed.")
    if normalized["confidence"] not in ALLOWED_CONFIDENCE:
        raise ValueError("AI output confidence is not allowed.")
    return normalized


def build_ai_trade_review(trade: TradeSignal, parsed: dict[str, str], raw_response: str) -> AiTradeReview:
    return AiTradeReview(
        trade_signal_id=trade.id,
        generated_at=local_now_naive(),
        symbol=trade.symbol,
        timeframe=trade.timeframe,
        strategy_version=trade.strategy_version,
        outcome=trade.outcome or "UNKNOWN",
        summary_vi=parsed["summary_vi"],
        failure_pattern=parsed["failure_pattern"],
        recommended_action=parsed["recommended_action"],
        suggested_rule_change=parsed["suggested_rule_change"],
        confidence=parsed["confidence"],
        risk_note=parsed["risk_note"],
        raw_response=raw_response,
    )


def format_ai_trade_review_message(review: AiTradeReview, trade: TradeSignal) -> str:
    outcome_label = {"WIN": "THẮNG", "LOSS": "THUA"}.get(trade.outcome or "", trade.outcome or "CHƯA RÕ")
    action_label = {
        "keep_strategy": "Giữ chiến lược",
        "tighten_filter": "Siết bộ lọc",
        "loosen_filter": "Nới bộ lọc",
        "disable_setup": "Tạm tắt setup",
        "needs_more_data": "Cần thêm dữ liệu",
    }.get(review.recommended_action, review.recommended_action)
    confidence_label = {"low": "Thấp", "medium": "Trung bình", "high": "Cao"}.get(
        review.confidence,
        review.confidence,
    )

    return (
        f"Phân tích AI cho lệnh #{trade.id} {trade.symbol} {trade.timeframe}\n"
        f"Kết quả: {outcome_label} | Side: {trade.side} | PnL: {(trade.pnl_r or 0):+.2f}R\n"
        f"Tóm tắt: {review.summary_vi}\n"
        f"Pattern lặp lại: {review.failure_pattern}\n"
        f"Hành động đề xuất: {action_label}\n"
        f"Đề xuất chỉnh rule: {review.suggested_rule_change}\n"
        f"Độ tin cậy: {confidence_label}\n"
        f"Lưu ý rủi ro: {review.risk_note}\n"
        f"Trạng thái: AI chỉ đề xuất, chưa tự áp dụng."
    )


def analyze_trade_with_ai(just_closed: TradeSignal, history: list[TradeSignal]) -> AiTradeReview:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured.")

    from openai import OpenAI

    payload = build_trade_analysis_payload(just_closed=just_closed, history=history)
    client = OpenAI(api_key=settings.openai_api_key)
    response = client.responses.create(
        model=settings.openai_text_model,
        input=[
            {
                "role": "system",
                "content": (
                    "Bạn là AI cố vấn phân tích trade price action/market structure. "
                    "Chỉ phân tích sau khi lệnh đã đóng, trả lời JSON thuần, tiếng Việt có dấu, "
                    "không đề xuất tự đặt lệnh và không tự thay đổi live strategy."
                ),
            },
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "ai_trade_review",
                "schema": AI_REVIEW_JSON_SCHEMA,
                "strict": True,
            }
        },
        max_output_tokens=900,
    )
    raw_response = response.output_text
    parsed = parse_ai_review_output(raw_response)
    return build_ai_trade_review(just_closed, parsed, raw_response)
