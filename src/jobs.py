from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from src.ai_trade_analyzer import analyze_trade_with_ai, format_ai_trade_review_message
from src.bitget_client import BitgetClient
from src.binance_client import Candle, fetch_klines
from src.config import settings
from src.models import AiTradeReview, DailySummary, StrategyInsight, TradeSignal
from src.strategy import build_signal
from src.storage import get_storage
from src.telegram_client import send_telegram_message
from src.time_utils import utc_to_local_naive


def init_storage():
    storage = get_storage()
    storage.init()
    return storage


def normalize_strategy_version(strategy_version: str | None) -> str:
    if strategy_version in {"v1", "v1_intraday", None, ""}:
        return "intraday"
    if strategy_version == "v1_swing":
        return "swing"
    return strategy_version


def format_signal_message(signal: TradeSignal) -> str:
    side_label = {"LONG": "MUA", "SHORT": "BÁN"}.get(signal.side, signal.side)
    bias_label = {"bullish": "Tăng", "bearish": "Giảm", "neutral": "Trung lập"}.get(signal.bias, signal.bias)
    strategy_version = normalize_strategy_version(signal.strategy_version)
    message = (
        f"[{signal.symbol}] Tín hiệu {side_label}\n"
        f"Xu hướng chính: {bias_label}\n"
        f"Khung vào lệnh: {signal.timeframe}\n"
        f"Loại setup: {strategy_version}\n"
        f"Điểm vào lệnh: {signal.entry_price:.2f}\n"
        f"SL: {signal.stop_loss:.2f}\n"
        f"TP: {signal.take_profit:.2f}\n"
        f"RR: {signal.risk_reward:.2f}\n"
        f"Điểm chất lượng: {signal.signal_score}\n"
        f"Lý do: {signal.reason}"
    )
    if signal.bitget_order_status:
        message += f"\nBitget: {signal.bitget_order_status}"
        if signal.bitget_order_id:
            message += f" | Order ID: {signal.bitget_order_id}"
        if signal.bitget_error:
            message += f" | Lỗi: {signal.bitget_error[:180]}"
    return message


def execute_bitget_order(signal: TradeSignal) -> None:
    if not settings.bitget_trading_enabled:
        signal.bitget_order_status = "DISABLED"
        return

    if not settings.bitget_api_key or not settings.bitget_api_secret or not settings.bitget_api_passphrase:
        signal.bitget_order_status = "SKIPPED"
        signal.bitget_error = "Thiếu BITGET_API_KEY, BITGET_API_SECRET hoặc BITGET_API_PASSPHRASE."
        return

    order_size = settings.bitget_order_size(signal.symbol)
    if not order_size:
        signal.bitget_order_status = "SKIPPED"
        signal.bitget_error = f"Thiếu BITGET_ORDER_SIZE_{signal.symbol} hoặc BITGET_DEFAULT_ORDER_SIZE."
        return

    client = BitgetClient(
        api_key=settings.bitget_api_key,
        api_secret=settings.bitget_api_secret,
        passphrase=settings.bitget_api_passphrase,
        base_url=settings.bitget_base_url,
    )
    try:
        bitget_symbol = settings.bitget_symbol(signal.symbol)
        leverage = settings.bitget_leverage(signal.symbol)
        if leverage:
            client.set_leverage(
                symbol=bitget_symbol,
                product_type=settings.bitget_product_type,
                margin_coin=settings.bitget_margin_coin,
                leverage=leverage,
            )
        result = client.place_market_order(
            symbol=bitget_symbol,
            side=signal.side,
            size=order_size,
            product_type=settings.bitget_product_type,
            margin_mode=settings.bitget_margin_mode,
            margin_coin=settings.bitget_margin_coin,
            take_profit=signal.take_profit,
            stop_loss=signal.stop_loss,
            client_oid_prefix=f"trade-{signal.id}",
        )
    except Exception as exc:
        signal.bitget_order_status = "FAILED"
        signal.bitget_error = str(exc)
        return

    signal.bitget_order_id = result.order_id
    signal.bitget_client_oid = result.client_oid
    signal.bitget_order_status = "PLACED"
    signal.bitget_error = None


def signal_scan_configs() -> list[dict[str, str | float | int]]:
    configs: list[dict[str, str | float | int]] = [
        {
            "label": "intraday",
            "timeframe": settings.timeframe,
            "higher_timeframe": settings.higher_timeframe,
            "risk_reward": settings.risk_reward,
            "min_signal_score": settings.min_signal_score,
            "strategy_version": "intraday",
        }
    ]
    if settings.swing_enabled:
        configs.append(
            {
                "label": "swing",
                "timeframe": settings.swing_timeframe,
                "higher_timeframe": settings.swing_higher_timeframe,
                "risk_reward": settings.swing_risk_reward,
                "min_signal_score": settings.swing_min_signal_score,
                "strategy_version": "swing",
            }
        )
    return configs


def strategy_min_score(strategy_version: str) -> int:
    if normalize_strategy_version(strategy_version) == "swing":
        return settings.swing_min_signal_score
    return settings.min_signal_score


def is_weekend_trade(trigger_time: datetime) -> bool:
    return trigger_time.weekday() >= 5


def run_signal_scan() -> str:
    storage = init_storage()
    created_signals: list[int] = []
    for symbol in settings.symbols:
        for config in signal_scan_configs():
            timeframe = str(config["timeframe"])
            higher_timeframe = str(config["higher_timeframe"])
            higher_tf = fetch_klines(symbol, higher_timeframe, limit=220)
            lower_tf = fetch_klines(symbol, timeframe, limit=300)
            setup = build_signal(
                lower_tf=lower_tf,
                higher_tf=higher_tf,
                risk_reward=float(config["risk_reward"]),
                min_signal_score=int(config["min_signal_score"]),
                execution_timeframe=timeframe,
                higher_timeframe=higher_timeframe,
                strategy_version=str(config["strategy_version"]),
            )
            if setup is None:
                continue

            trigger_time = utc_to_local_naive(datetime.fromisoformat(setup.trigger_candle_time))
            if is_weekend_trade(trigger_time):
                continue
            if storage.open_trade_count(symbol, timeframe) >= settings.max_open_trades_per_timeframe:
                continue
            if storage.latest_duplicate(symbol, setup.side, trigger_time, timeframe):
                continue

            signal = TradeSignal(
                symbol=symbol,
                timeframe=timeframe,
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
            signal = storage.create_trade_signal(signal)

            execute_bitget_order(signal)
            signal = storage.update_trade_signal(signal)

            send_telegram_message(
                settings.telegram_bot_token,
                settings.telegram_chat_id,
                format_signal_message(signal),
            )
            signal.telegram_sent = True
            storage.update_trade_signal(signal)
            created_signals.append(signal.id)

    if not created_signals:
        return "No trade setup found."
    return f"Created signals: {', '.join(str(signal_id) for signal_id in created_signals)}."


def resolve_trade_with_candles(trade: TradeSignal, candles: list[Candle]) -> tuple[str, float, datetime] | None:
    for candle in candles:
        candle_open_time = utc_to_local_naive(candle.open_time)
        if candle_open_time <= trade.signal_time:
            continue
        candle_close_time = utc_to_local_naive(candle.close_time)
        if trade.side == "LONG":
            hit_sl = candle.low <= trade.stop_loss
            hit_tp = candle.high >= trade.take_profit
            if hit_sl and hit_tp:
                return "LOSS", trade.stop_loss, candle_close_time
            if hit_sl:
                return "LOSS", trade.stop_loss, candle_close_time
            if hit_tp:
                return "WIN", trade.take_profit, candle_close_time
        else:
            hit_sl = candle.high >= trade.stop_loss
            hit_tp = candle.low <= trade.take_profit
            if hit_sl and hit_tp:
                return "LOSS", trade.stop_loss, candle_close_time
            if hit_sl:
                return "LOSS", trade.stop_loss, candle_close_time
            if hit_tp:
                return "WIN", trade.take_profit, candle_close_time
    return None


def build_recommendation(closed_trades: list[TradeSignal], winrate: float) -> str:
    if not closed_trades:
        return "Chưa có đủ dữ liệu để đưa ra đề xuất."

    score_threshold = strategy_min_score(closed_trades[0].strategy_version)
    by_side = Counter(trade.side for trade in closed_trades if trade.outcome == "LOSS")
    by_score = Counter(
        "low_score" if trade.signal_score <= score_threshold else "high_score"
        for trade in closed_trades
        if trade.outcome == "LOSS"
    )
    recommendations: list[str] = []

    if winrate < settings.winrate_alert_threshold:
        recommendations.append("Winrate đang dưới ngưỡng, nên lọc chặt hơn các lệnh có điểm thấp.")
        if by_score["low_score"] >= by_score["high_score"]:
            recommendations.append(f"Tăng MIN_SIGNAL_SCORE lên {score_threshold + 1} để loại bớt các setup yếu.")
        if by_side["LONG"] > by_side["SHORT"]:
            recommendations.append("Lệnh LONG đang thua nhiều hơn, nên ưu tiên giao dịch khi xu hướng giảm thật rõ.")
        elif by_side["SHORT"] > by_side["LONG"]:
            recommendations.append("Lệnh SHORT đang thua nhiều hơn, nên ưu tiên giao dịch khi xu hướng tăng thật rõ.")
        recommendations.append("Có thể thêm bộ lọc ATR hoặc chỉ giao dịch khi volume cao hơn trung bình 20 nến.")
    else:
        recommendations.append("Winrate đang ổn. Tạm thời giữ nguyên logic và tiếp tục thu thập thêm dữ liệu.")

    return " ".join(recommendations)


def recent_eth_closed_history(trade: TradeSignal, all_closed_trades: list[TradeSignal]) -> list[TradeSignal]:
    if trade.symbol.upper() != "ETHUSDT":
        return []

    by_id = {
        candidate.id: candidate
        for candidate in all_closed_trades
        if candidate.id is not None and candidate.symbol.upper() == "ETHUSDT" and candidate.status == "CLOSED"
    }
    if trade.id is not None:
        by_id[trade.id] = trade

    return sorted(
        by_id.values(),
        key=lambda item: item.close_time or datetime.min,
        reverse=True,
    )[: settings.ai_analysis_lookback]


def maybe_send_ai_trade_reviews(
    storage,
    recently_closed: list[TradeSignal],
    all_closed_trades: list[TradeSignal],
    analyzer=analyze_trade_with_ai,
    sender=send_telegram_message,
) -> list[AiTradeReview]:
    if not settings.ai_trade_analysis_enabled or not settings.openai_api_key:
        return []

    reviews: list[AiTradeReview] = []
    for trade in recently_closed:
        history = recent_eth_closed_history(trade, all_closed_trades)
        if len(history) < settings.ai_min_closed_trades:
            continue
        try:
            review = analyzer(trade, history)
            review = storage.upsert_ai_trade_review(review)
            sender(
                settings.telegram_bot_token,
                settings.telegram_chat_id,
                format_ai_trade_review_message(review, trade),
            )
            reviews.append(review)
        except Exception:
            continue
    return reviews


def format_closed_trade_detail(trade: TradeSignal) -> str:
    strategy_version = normalize_strategy_version(trade.strategy_version)
    side_label = {"LONG": "MUA", "SHORT": "BÁN"}.get(trade.side, trade.side)
    outcome_label = {"WIN": "THẮNG", "LOSS": "THUA"}.get(trade.outcome or "", trade.outcome or "CHƯA RÕ")
    close_reason = "Chạm TP" if trade.outcome == "WIN" else "Chạm SL" if trade.outcome == "LOSS" else "Đã đóng"
    close_time = trade.close_time.strftime("%Y-%m-%d %H:%M") if trade.close_time else "Không rõ"
    close_price = trade.close_price if trade.close_price is not None else 0.0
    pnl_r = trade.pnl_r if trade.pnl_r is not None else 0.0
    return (
        f"#{trade.id} {strategy_version} {trade.timeframe} {side_label}: {outcome_label} ({close_reason})\n"
        f"Thời gian đóng: {close_time}\n"
        f"Entry: {trade.entry_price:.2f} | Giá đóng: {close_price:.2f} | PnL: {pnl_r:+.2f}R\n"
        f"SL: {trade.stop_loss:.2f} | TP: {trade.take_profit:.2f}"
    )


def _run_trade_evaluation_sql_legacy() -> str:
    init_db()
    with SessionLocal() as session:
        open_trades = session.execute(select(TradeSignal).where(TradeSignal.status == "OPEN")).scalars().all()
        candles_by_timeframe: dict[tuple[str, str], list[Candle]] = {}
        closed_now = 0
        for trade in open_trades:
            candle_key = (trade.symbol, trade.timeframe)
            if candle_key not in candles_by_timeframe:
                candles_by_timeframe[candle_key] = fetch_klines(trade.symbol, trade.timeframe, limit=500)
            result = resolve_trade_with_candles(trade, candles_by_timeframe[candle_key])
            if result is None:
                continue
            outcome, close_price, close_time = result
            trade.status = "CLOSED"
            trade.outcome = outcome
            trade.close_price = close_price
            trade.close_time = close_time
            trade.pnl_r = trade.risk_reward if outcome == "WIN" else -1.0
            trade.strategy_version = normalize_strategy_version(trade.strategy_version)
            closed_now += 1

        session.commit()

        all_closed_trades = session.execute(
            select(TradeSignal).where(TradeSignal.status == "CLOSED")
        ).scalars().all()
        if not all_closed_trades:
            return "No closed trades available yet."

        recently_closed = [trade for trade in open_trades if trade.status == "CLOSED"]
        strategy_summaries: dict[str, tuple[float, int, str]] = {}
        for trade in recently_closed:
            closed_trades = [
                candidate
                for candidate in sorted(
                    all_closed_trades,
                    key=lambda item: item.close_time or datetime.min,
                    reverse=True,
                )
                if normalize_strategy_version(candidate.strategy_version) == normalize_strategy_version(trade.strategy_version)
            ][:30]
            wins = sum(1 for candidate in closed_trades if candidate.outcome == "WIN")
            winrate = round((wins / len(closed_trades)) * 100, 2)
            recommendation = build_recommendation(closed_trades, winrate)
            strategy_version = normalize_strategy_version(trade.strategy_version)
            strategy_summaries[strategy_version] = (winrate, len(closed_trades), recommendation)
            insight = session.execute(
                select(StrategyInsight).where(StrategyInsight.trade_signal_id == trade.id)
            ).scalar_one_or_none()
            if insight is None:
                insight = StrategyInsight(
                    trade_signal_id=trade.id,
                    scope=strategy_version,
                    winrate=winrate,
                    total_trades=len(closed_trades),
                    recommendation=recommendation,
                )
                session.add(insight)
            else:
                insight.scope = strategy_version
                insight.winrate = winrate
                insight.total_trades = len(closed_trades)
                insight.recommendation = recommendation
        session.commit()

        if closed_now > 0:
            detail_lines = [format_closed_trade_detail(trade) for trade in recently_closed]
            summary_lines = []
            for strategy_version, (winrate, total_trades, recommendation) in sorted(strategy_summaries.items()):
                summary_lines.append(
                    f"{strategy_version}: {winrate:.2f}% trên {total_trades} lệnh. Đề xuất: {recommendation}"
                )
            send_telegram_message(
                settings.telegram_bot_token,
                settings.telegram_chat_id,
                (
                    f"Cập nhật kết quả lệnh.\n"
                    f"Số lệnh vừa đóng: {closed_now}\n"
                    f"Chi tiết lệnh vừa đóng:\n"
                    + "\n\n".join(detail_lines)
                    + "\n\nWinrate cập nhật:\n"
                    + "\n".join(summary_lines)
                ),
            )
        if strategy_summaries:
            compact = ", ".join(
                f"{strategy_version}={winrate:.2f}%/{total_trades}"
                for strategy_version, (winrate, total_trades, _) in sorted(strategy_summaries.items())
            )
            return f"Closed now: {closed_now}. Strategy winrates: {compact}."
        return f"Closed now: {closed_now}."


def _run_daily_summary_sql_legacy() -> str:
    init_db()
    tz = ZoneInfo(settings.timezone)
    now_local = datetime.now(tz)
    target_date = (now_local - timedelta(days=1)).date()
    start_local = datetime(target_date.year, target_date.month, target_date.day)
    end_local = start_local + timedelta(days=1)

    with SessionLocal() as session:
        trades = session.execute(
            select(TradeSignal).where(
                TradeSignal.status == "CLOSED",
                TradeSignal.close_time >= start_local,
                TradeSignal.close_time < end_local,
            )
        ).scalars().all()

        total = len(trades)
        wins = sum(1 for trade in trades if trade.outcome == "WIN")
        losses = sum(1 for trade in trades if trade.outcome == "LOSS")
        total_r = round(sum(trade.pnl_r or 0 for trade in trades), 2)
        winrate = round((wins / total) * 100, 2) if total else 0.0
        notes = (
            "Ngày này không có lệnh đóng."
            if total == 0
            else "Báo cáo tự động theo kết quả các lệnh đã đóng trong ngày."
        )

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
            (
                f"Báo cáo ngày {target_date}\n"
                f"Tổng lệnh: {total}\n"
                f"Lệnh thắng: {wins}\n"
                f"Lệnh thua: {losses}\n"
                f"Winrate: {winrate:.2f}%\n"
                f"Tổng R: {total_r:.2f}"
            ),
        )
        return f"Daily summary updated for {target_date}."


def run_trade_evaluation() -> str:
    storage = init_storage()
    open_trades = storage.list_open_trades()
    candles_by_timeframe: dict[tuple[str, str], list[Candle]] = {}
    recently_closed: list[TradeSignal] = []
    for trade in open_trades:
        candle_key = (trade.symbol, trade.timeframe)
        if candle_key not in candles_by_timeframe:
            candles_by_timeframe[candle_key] = fetch_klines(trade.symbol, trade.timeframe, limit=500)
        result = resolve_trade_with_candles(trade, candles_by_timeframe[candle_key])
        if result is None:
            continue
        outcome, close_price, close_time = result
        trade.status = "CLOSED"
        trade.outcome = outcome
        trade.close_price = close_price
        trade.close_time = close_time
        trade.pnl_r = trade.risk_reward if outcome == "WIN" else -1.0
        trade.strategy_version = normalize_strategy_version(trade.strategy_version)
        storage.update_trade_signal(trade)
        recently_closed.append(trade)

    closed_now = len(recently_closed)
    if closed_now == 0:
        return "Closed now: 0."

    all_closed_trades = storage.list_closed_trades()
    if not all_closed_trades:
        return "No closed trades available yet."

    strategy_summaries: dict[str, tuple[float, int, str]] = {}
    for trade in recently_closed:
        closed_trades = [
            candidate
            for candidate in sorted(
                all_closed_trades,
                key=lambda item: item.close_time or datetime.min,
                reverse=True,
            )
            if normalize_strategy_version(candidate.strategy_version) == normalize_strategy_version(trade.strategy_version)
        ][:30]
        wins = sum(1 for candidate in closed_trades if candidate.outcome == "WIN")
        winrate = round((wins / len(closed_trades)) * 100, 2)
        recommendation = build_recommendation(closed_trades, winrate)
        strategy_version = normalize_strategy_version(trade.strategy_version)
        strategy_summaries[strategy_version] = (winrate, len(closed_trades), recommendation)
        storage.upsert_strategy_insight(
            StrategyInsight(
                trade_signal_id=trade.id,
                scope=strategy_version,
                winrate=winrate,
                total_trades=len(closed_trades),
                recommendation=recommendation,
            )
        )

    detail_lines = [format_closed_trade_detail(trade) for trade in recently_closed]
    summary_lines = []
    for strategy_version, (winrate, total_trades, recommendation) in sorted(strategy_summaries.items()):
        summary_lines.append(
            f"{strategy_version}: {winrate:.2f}% trên {total_trades} lệnh. Đề xuất: {recommendation}"
        )
    send_telegram_message(
        settings.telegram_bot_token,
        settings.telegram_chat_id,
        (
            f"Cập nhật kết quả lệnh.\n"
            f"Số lệnh vừa đóng: {closed_now}\n"
            f"Chi tiết lệnh vừa đóng:\n"
            + "\n\n".join(detail_lines)
            + "\n\nWinrate cập nhật:\n"
            + "\n".join(summary_lines)
        ),
    )
    try:
        maybe_send_ai_trade_reviews(storage, recently_closed, all_closed_trades)
    except Exception:
        pass
    compact = ", ".join(
        f"{strategy_version}={winrate:.2f}%/{total_trades}"
        for strategy_version, (winrate, total_trades, _) in sorted(strategy_summaries.items())
    )
    return f"Closed now: {closed_now}. Strategy winrates: {compact}."


def run_daily_summary() -> str:
    storage = init_storage()
    tz = ZoneInfo(settings.timezone)
    now_local = datetime.now(tz)
    target_date = (now_local - timedelta(days=1)).date()
    start_local = datetime(target_date.year, target_date.month, target_date.day)
    end_local = start_local + timedelta(days=1)

    trades = storage.list_closed_trades_between(start_local, end_local)
    total = len(trades)
    wins = sum(1 for trade in trades if trade.outcome == "WIN")
    losses = sum(1 for trade in trades if trade.outcome == "LOSS")
    total_r = round(sum(trade.pnl_r or 0 for trade in trades), 2)
    winrate = round((wins / total) * 100, 2) if total else 0.0
    notes = (
        "Ngày này không có lệnh đóng."
        if total == 0
        else "Báo cáo tự động theo kết quả các lệnh đã đóng trong ngày."
    )

    storage.upsert_daily_summary(
        DailySummary(
            summary_date=target_date,
            total_trades=total,
            wins=wins,
            losses=losses,
            winrate=winrate,
            total_r=total_r,
            notes=notes,
        )
    )

    send_telegram_message(
        settings.telegram_bot_token,
        settings.telegram_chat_id,
        (
            f"Báo cáo ngày {target_date}\n"
            f"Tổng lệnh: {total}\n"
            f"Lệnh thắng: {wins}\n"
            f"Lệnh thua: {losses}\n"
            f"Winrate: {winrate:.2f}%\n"
            f"Tổng R: {total_r:.2f}"
        ),
    )
    return f"Daily summary updated for {target_date}."
