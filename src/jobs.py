from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import desc, select

from src.binance_client import Candle, fetch_klines
from src.config import settings
from src.db import Base, SessionLocal, engine
from src.models import DailySummary, StrategyInsight, TradeSignal
from src.strategy import build_signal
from src.telegram_client import send_telegram_message


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def has_open_trade(session) -> bool:
    stmt = select(TradeSignal).where(TradeSignal.symbol == settings.symbol, TradeSignal.status == "OPEN")
    return session.execute(stmt).scalar_one_or_none() is not None


def latest_duplicate(session, side: str, trigger_time: datetime) -> bool:
    stmt = (
        select(TradeSignal)
        .where(TradeSignal.symbol == settings.symbol, TradeSignal.side == side)
        .order_by(desc(TradeSignal.signal_time))
        .limit(1)
    )
    signal = session.execute(stmt).scalar_one_or_none()
    if signal is None:
        return False
    return abs((signal.signal_time - trigger_time.replace(tzinfo=None)).total_seconds()) < 60 * 60


def format_signal_message(signal: TradeSignal) -> str:
    return (
        f"[{signal.symbol}] Tín hiệu {signal.side}\n"
        f"Xu hướng chính: {signal.bias}\n"
        f"Khung thời gian: {signal.timeframe}\n"
        f"Điểm vào lệnh: {signal.entry_price:.2f}\n"
        f"SL: {signal.stop_loss:.2f}\n"
        f"TP: {signal.take_profit:.2f}\n"
        f"RR: {signal.risk_reward:.2f}\n"
        f"Điểm chất lượng: {signal.signal_score}\n"
        f"Lý do: {signal.reason}"
    )


def run_signal_scan() -> str:
    init_db()
    higher_tf = fetch_klines(settings.symbol, settings.higher_timeframe, limit=220)
    lower_tf = fetch_klines(settings.symbol, settings.timeframe, limit=300)
    setup = build_signal(lower_tf, higher_tf, settings.risk_reward, settings.min_signal_score)
    if setup is None:
        return "No trade setup found."

    trigger_time = datetime.fromisoformat(setup.trigger_candle_time).astimezone(UTC).replace(tzinfo=None)
    with SessionLocal() as session:
        if has_open_trade(session):
            return "Skipped because an open trade already exists."
        if latest_duplicate(session, setup.side, trigger_time):
            return "Skipped duplicate signal."

        signal = TradeSignal(
            symbol=settings.symbol,
            timeframe=settings.timeframe,
            side=setup.side,
            status="OPEN",
            bias=setup.bias,
            strategy_version=setup.strategy_version,
            signal_time=trigger_time,
            entry_price=setup.entry_price,
            stop_loss=setup.stop_loss,
            take_profit=setup.take_profit,
            risk_reward=setup.risk_reward,
            signal_score=setup.signal_score,
            reason=setup.reason,
            setup_json=setup.to_json(),
        )
        session.add(signal)
        session.commit()
        session.refresh(signal)

        send_telegram_message(
            settings.telegram_bot_token,
            settings.telegram_chat_id,
            format_signal_message(signal),
        )
        signal.telegram_sent = True
        session.commit()
        return f"Created signal #{signal.id}."


def resolve_trade_with_candles(trade: TradeSignal, candles: list[Candle]) -> tuple[str, float, datetime] | None:
    for candle in candles:
        if candle.open_time.replace(tzinfo=None) <= trade.signal_time:
            continue
        if trade.side == "LONG":
            hit_sl = candle.low <= trade.stop_loss
            hit_tp = candle.high >= trade.take_profit
            if hit_sl and hit_tp:
                return "LOSS", trade.stop_loss, candle.close_time.replace(tzinfo=None)
            if hit_sl:
                return "LOSS", trade.stop_loss, candle.close_time.replace(tzinfo=None)
            if hit_tp:
                return "WIN", trade.take_profit, candle.close_time.replace(tzinfo=None)
        else:
            hit_sl = candle.high >= trade.stop_loss
            hit_tp = candle.low <= trade.take_profit
            if hit_sl and hit_tp:
                return "LOSS", trade.stop_loss, candle.close_time.replace(tzinfo=None)
            if hit_sl:
                return "LOSS", trade.stop_loss, candle.close_time.replace(tzinfo=None)
            if hit_tp:
                return "WIN", trade.take_profit, candle.close_time.replace(tzinfo=None)
    return None


def build_recommendation(closed_trades: list[TradeSignal], winrate: float) -> str:
    if not closed_trades:
        return "Chưa có đủ dữ liệu để đưa ra đề xuất."

    by_side = Counter(trade.side for trade in closed_trades if trade.outcome == "LOSS")
    by_score = Counter("low_score" if trade.signal_score <= settings.min_signal_score else "high_score" for trade in closed_trades if trade.outcome == "LOSS")
    recommendations: list[str] = []

    if winrate < settings.winrate_alert_threshold:
        recommendations.append("Winrate đang dưới ngưỡng, nên lọc chặt hơn các lệnh có điểm thấp.")
        if by_score["low_score"] >= by_score["high_score"]:
            recommendations.append(f"Tăng MIN_SIGNAL_SCORE lên {settings.min_signal_score + 1} để loại bớt các setup yếu.")
        if by_side["LONG"] > by_side["SHORT"]:
            recommendations.append("Lệnh LONG đang thua nhiều hơn, nên ưu tiên giao dịch khi xu hướng giảm thật rõ.")
        elif by_side["SHORT"] > by_side["LONG"]:
            recommendations.append("Lệnh SHORT đang thua nhiều hơn, nên ưu tiên giao dịch khi xu hướng tăng thật rõ.")
        recommendations.append("Có thể thêm bộ lọc ATR hoặc chỉ giao dịch khi volume cao hơn trung bình 20 nến.")
    else:
        recommendations.append("Winrate đang ổn. Tạm thời giữ nguyên logic và tiếp tục thu thập thêm dữ liệu.")

    return " ".join(recommendations)


def run_trade_evaluation() -> str:
    init_db()
    with SessionLocal() as session:
        open_trades = session.execute(select(TradeSignal).where(TradeSignal.status == "OPEN")).scalars().all()
        candles = fetch_klines(settings.symbol, settings.timeframe, limit=500)
        closed_now = 0
        for trade in open_trades:
            result = resolve_trade_with_candles(trade, candles)
            if result is None:
                continue
            outcome, close_price, close_time = result
            trade.status = "CLOSED"
            trade.outcome = outcome
            trade.close_price = close_price
            trade.close_time = close_time
            trade.pnl_r = trade.risk_reward if outcome == "WIN" else -1.0
            closed_now += 1

        session.commit()

        closed_trades = session.execute(
            select(TradeSignal)
            .where(TradeSignal.status == "CLOSED")
            .order_by(desc(TradeSignal.close_time))
            .limit(30)
        ).scalars().all()
        if not closed_trades:
            return "No closed trades available yet."

        wins = sum(1 for trade in closed_trades if trade.outcome == "WIN")
        winrate = round((wins / len(closed_trades)) * 100, 2)
        recommendation = build_recommendation(closed_trades, winrate)
        session.add(
            StrategyInsight(
                scope="rolling_30",
                winrate=winrate,
                total_trades=len(closed_trades),
                recommendation=recommendation,
            )
        )
        session.commit()

        if closed_now > 0:
            send_telegram_message(
                settings.telegram_bot_token,
                settings.telegram_chat_id,
                f"Cập nhật kết quả lệnh.\nSố lệnh vừa đóng: {closed_now}\nWinrate 30 lệnh gần nhất: {winrate:.2f}%\nĐề xuất: {recommendation}",
            )
        return f"Closed now: {closed_now}. Rolling winrate: {winrate:.2f}%."


def run_daily_summary() -> str:
    init_db()
    tz = ZoneInfo(settings.timezone)
    now_local = datetime.now(tz)
    target_date = (now_local - timedelta(days=1)).date()
    start_local = datetime(target_date.year, target_date.month, target_date.day, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    start_utc = start_local.astimezone(UTC).replace(tzinfo=None)
    end_utc = end_local.astimezone(UTC).replace(tzinfo=None)

    with SessionLocal() as session:
        trades = session.execute(
            select(TradeSignal).where(
                TradeSignal.status == "CLOSED",
                TradeSignal.close_time >= start_utc,
                TradeSignal.close_time < end_utc,
            )
        ).scalars().all()

        total = len(trades)
        wins = sum(1 for trade in trades if trade.outcome == "WIN")
        losses = sum(1 for trade in trades if trade.outcome == "LOSS")
        total_r = round(sum(trade.pnl_r or 0 for trade in trades), 2)
        winrate = round((wins / total) * 100, 2) if total else 0.0
        notes = "Ngày này không có lệnh đóng." if total == 0 else "Báo cáo tự động theo kết quả các lệnh đã đóng trong ngày."

        existing = session.execute(select(DailySummary).where(DailySummary.summary_date == target_date)).scalar_one_or_none()
        if existing is None:
            existing = DailySummary(
                summary_date=target_date,
                total_trades=total,
                wins=wins,
                losses=losses,
                winrate=winrate,
                total_r=total_r,
                notes=notes,
            )
            session.add(existing)
        else:
            existing.total_trades = total
            existing.wins = wins
            existing.losses = losses
            existing.winrate = winrate
            existing.total_r = total_r
            existing.notes = notes
        session.commit()

        send_telegram_message(
            settings.telegram_bot_token,
            settings.telegram_chat_id,
            f"Báo cáo ngày {target_date}\nTổng lệnh: {total}\nLệnh thắng: {wins}\nLệnh thua: {losses}\nWinrate: {winrate:.2f}%\nTổng R: {total_r:.2f}",
        )
        return f"Daily summary updated for {target_date}."
