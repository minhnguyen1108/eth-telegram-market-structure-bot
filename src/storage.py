from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Protocol

from sqlalchemy import desc, select

from src.config import settings
from src.db import Base, SessionLocal, engine, ensure_schema_updates
from src.models import DailySummary, StrategyInsight, TradeSignal
from src.time_utils import local_now_naive


class TradeStorage(Protocol):
    def init(self) -> None: ...
    def open_trade_count(self, symbol: str, timeframe: str) -> int: ...
    def latest_duplicate(self, symbol: str, side: str, trigger_time: datetime, timeframe: str) -> bool: ...
    def create_trade_signal(self, signal: TradeSignal) -> TradeSignal: ...
    def update_trade_signal(self, signal: TradeSignal) -> TradeSignal: ...
    def list_open_trades(self) -> list[TradeSignal]: ...
    def list_closed_trades(self) -> list[TradeSignal]: ...
    def list_closed_trades_between(self, start_local: datetime, end_local: datetime) -> list[TradeSignal]: ...
    def upsert_strategy_insight(self, insight: StrategyInsight) -> StrategyInsight: ...
    def upsert_daily_summary(self, summary: DailySummary) -> DailySummary: ...


def normalize_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, str):
        return datetime.fromisoformat(value).replace(tzinfo=None)
    return value


def normalize_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return date.fromisoformat(str(value))


def trade_signal_to_document(signal: TradeSignal) -> dict[str, Any]:
    return {
        "id": signal.id,
        "symbol": signal.symbol,
        "timeframe": signal.timeframe,
        "side": signal.side,
        "status": signal.status,
        "bias": signal.bias,
        "strategy_version": signal.strategy_version,
        "signal_time": signal.signal_time,
        "entry_price": signal.entry_price,
        "stop_loss": signal.stop_loss,
        "take_profit": signal.take_profit,
        "risk_reward": signal.risk_reward,
        "signal_score": signal.signal_score,
        "reason": signal.reason,
        "setup_json": signal.setup_json,
        "close_time": signal.close_time,
        "close_price": signal.close_price,
        "outcome": signal.outcome,
        "pnl_r": signal.pnl_r,
        "telegram_sent": signal.telegram_sent,
        "bitget_order_id": signal.bitget_order_id,
        "bitget_client_oid": signal.bitget_client_oid,
        "bitget_order_status": signal.bitget_order_status,
        "bitget_error": signal.bitget_error,
        "created_at": signal.created_at or local_now_naive(),
        "updated_at": local_now_naive(),
        "duplicate_key": f"{signal.symbol}:{signal.side}:{signal.timeframe}",
    }


def trade_signal_from_document(document: dict[str, Any]) -> TradeSignal:
    return TradeSignal(
        id=int(document["id"]),
        symbol=document["symbol"],
        timeframe=document["timeframe"],
        side=document["side"],
        status=document["status"],
        bias=document["bias"],
        strategy_version=document.get("strategy_version", "intraday"),
        signal_time=normalize_datetime(document["signal_time"]),
        entry_price=float(document["entry_price"]),
        stop_loss=float(document["stop_loss"]),
        take_profit=float(document["take_profit"]),
        risk_reward=float(document["risk_reward"]),
        signal_score=int(document["signal_score"]),
        reason=document["reason"],
        setup_json=document["setup_json"],
        close_time=normalize_datetime(document.get("close_time")),
        close_price=document.get("close_price"),
        outcome=document.get("outcome"),
        pnl_r=document.get("pnl_r"),
        telegram_sent=bool(document.get("telegram_sent", False)),
        bitget_order_id=document.get("bitget_order_id"),
        bitget_client_oid=document.get("bitget_client_oid"),
        bitget_order_status=document.get("bitget_order_status"),
        bitget_error=document.get("bitget_error"),
        created_at=normalize_datetime(document.get("created_at")) or local_now_naive(),
        updated_at=normalize_datetime(document.get("updated_at")) or local_now_naive(),
    )


def strategy_insight_to_document(insight: StrategyInsight) -> dict[str, Any]:
    return {
        "id": insight.id,
        "trade_signal_id": insight.trade_signal_id,
        "generated_at": insight.generated_at or local_now_naive(),
        "scope": insight.scope,
        "winrate": insight.winrate,
        "total_trades": insight.total_trades,
        "recommendation": insight.recommendation,
    }


def strategy_insight_from_document(document: dict[str, Any]) -> StrategyInsight:
    return StrategyInsight(
        id=document.get("id"),
        trade_signal_id=int(document["trade_signal_id"]),
        generated_at=normalize_datetime(document.get("generated_at")) or local_now_naive(),
        scope=document.get("scope", "rolling_30"),
        winrate=float(document["winrate"]),
        total_trades=int(document["total_trades"]),
        recommendation=document["recommendation"],
    )


def daily_summary_to_document(summary: DailySummary) -> dict[str, Any]:
    return {
        "id": summary.id,
        "summary_date": summary.summary_date.isoformat(),
        "total_trades": summary.total_trades,
        "wins": summary.wins,
        "losses": summary.losses,
        "winrate": summary.winrate,
        "total_r": summary.total_r,
        "notes": summary.notes,
        "created_at": summary.created_at or local_now_naive(),
    }


def daily_summary_from_document(document: dict[str, Any]) -> DailySummary:
    return DailySummary(
        id=document.get("id"),
        summary_date=normalize_date(document["summary_date"]),
        total_trades=int(document["total_trades"]),
        wins=int(document["wins"]),
        losses=int(document["losses"]),
        winrate=float(document["winrate"]),
        total_r=float(document["total_r"]),
        notes=document["notes"],
        created_at=normalize_datetime(document.get("created_at")) or local_now_naive(),
    )


class SqlStorage:
    def init(self) -> None:
        Base.metadata.create_all(bind=engine)
        ensure_schema_updates()

    def open_trade_count(self, symbol: str, timeframe: str) -> int:
        with SessionLocal() as session:
            stmt = select(TradeSignal).where(
                TradeSignal.symbol == symbol,
                TradeSignal.status == "OPEN",
                TradeSignal.timeframe == timeframe,
            )
            return len(session.execute(stmt).scalars().all())

    def latest_duplicate(self, symbol: str, side: str, trigger_time: datetime, timeframe: str) -> bool:
        with SessionLocal() as session:
            stmt = (
                select(TradeSignal)
                .where(
                    TradeSignal.symbol == symbol,
                    TradeSignal.side == side,
                    TradeSignal.timeframe == timeframe,
                )
                .order_by(desc(TradeSignal.signal_time))
                .limit(1)
            )
            signal = session.execute(stmt).scalar_one_or_none()
            if signal is None:
                return False
            return abs((signal.signal_time - trigger_time).total_seconds()) < 60 * 60

    def create_trade_signal(self, signal: TradeSignal) -> TradeSignal:
        with SessionLocal() as session:
            session.add(signal)
            session.commit()
            session.refresh(signal)
            session.expunge(signal)
            return signal

    def update_trade_signal(self, signal: TradeSignal) -> TradeSignal:
        with SessionLocal() as session:
            merged = session.merge(signal)
            session.commit()
            session.refresh(merged)
            session.expunge(merged)
            return merged

    def list_open_trades(self) -> list[TradeSignal]:
        with SessionLocal() as session:
            trades = session.execute(select(TradeSignal).where(TradeSignal.status == "OPEN")).scalars().all()
            for trade in trades:
                session.expunge(trade)
            return trades

    def list_closed_trades(self) -> list[TradeSignal]:
        with SessionLocal() as session:
            trades = session.execute(select(TradeSignal).where(TradeSignal.status == "CLOSED")).scalars().all()
            for trade in trades:
                session.expunge(trade)
            return trades

    def list_closed_trades_between(self, start_local: datetime, end_local: datetime) -> list[TradeSignal]:
        with SessionLocal() as session:
            trades = session.execute(
                select(TradeSignal).where(
                    TradeSignal.status == "CLOSED",
                    TradeSignal.close_time >= start_local,
                    TradeSignal.close_time < end_local,
                )
            ).scalars().all()
            for trade in trades:
                session.expunge(trade)
            return trades

    def upsert_strategy_insight(self, insight: StrategyInsight) -> StrategyInsight:
        with SessionLocal() as session:
            existing = session.execute(
                select(StrategyInsight).where(StrategyInsight.trade_signal_id == insight.trade_signal_id)
            ).scalar_one_or_none()
            if existing is None:
                session.add(insight)
                target = insight
            else:
                existing.scope = insight.scope
                existing.winrate = insight.winrate
                existing.total_trades = insight.total_trades
                existing.recommendation = insight.recommendation
                target = existing
            session.commit()
            session.refresh(target)
            session.expunge(target)
            return target

    def upsert_daily_summary(self, summary: DailySummary) -> DailySummary:
        with SessionLocal() as session:
            existing = session.execute(
                select(DailySummary).where(DailySummary.summary_date == summary.summary_date)
            ).scalar_one_or_none()
            if existing is None:
                session.add(summary)
                target = summary
            else:
                existing.total_trades = summary.total_trades
                existing.wins = summary.wins
                existing.losses = summary.losses
                existing.winrate = summary.winrate
                existing.total_r = summary.total_r
                existing.notes = summary.notes
                target = existing
            session.commit()
            session.refresh(target)
            session.expunge(target)
            return target


class FirestoreStorage:
    def __init__(self) -> None:
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from google.cloud import firestore
            from google.oauth2 import service_account

            project_id = settings.firebase_project_id
            credentials = None
            if settings.firebase_service_account_json:
                info = json.loads(settings.firebase_service_account_json)
                project_id = project_id or info.get("project_id", "")
                credentials = service_account.Credentials.from_service_account_info(info)
            self._client = firestore.Client(project=project_id or None, credentials=credentials)
        return self._client

    def init(self) -> None:
        self.collection("app_metadata").document("storage").set(
            {"backend": "firestore", "updated_at": local_now_naive()},
            merge=True,
        )

    def collection(self, name: str):
        prefix = settings.firestore_collection_prefix.strip()
        return self.client.collection(f"{prefix}_{name}" if prefix else name)

    def next_id(self, counter_name: str) -> int:
        from google.cloud import firestore

        counter_ref = self.collection("app_metadata").document("counters")
        transaction = self.client.transaction()

        @firestore.transactional
        def increment(transaction):
            snapshot = counter_ref.get(transaction=transaction)
            data = snapshot.to_dict() if snapshot.exists else {}
            value = int(data.get(counter_name, 0)) + 1
            transaction.set(counter_ref, {counter_name: value}, merge=True)
            return value

        return increment(transaction)

    def open_trade_count(self, symbol: str, timeframe: str) -> int:
        return sum(
            1
            for trade in self.list_open_trades()
            if trade.symbol == symbol and trade.timeframe == timeframe
        )

    def latest_duplicate(self, symbol: str, side: str, trigger_time: datetime, timeframe: str) -> bool:
        duplicate_key = f"{symbol}:{side}:{timeframe}"
        matching = [
            trade_signal_from_document(snapshot.to_dict())
            for snapshot in self.collection("trade_signals").where("duplicate_key", "==", duplicate_key).stream()
        ]
        if not matching:
            return False
        latest = max(matching, key=lambda signal: signal.signal_time)
        return abs((latest.signal_time - trigger_time).total_seconds()) < 60 * 60

    def create_trade_signal(self, signal: TradeSignal) -> TradeSignal:
        if signal.id is None:
            signal.id = self.next_id("trade_signal_id")
        now = local_now_naive()
        signal.created_at = signal.created_at or now
        signal.updated_at = now
        self.collection("trade_signals").document(str(signal.id)).set(trade_signal_to_document(signal))
        return signal

    def update_trade_signal(self, signal: TradeSignal) -> TradeSignal:
        signal.updated_at = local_now_naive()
        self.collection("trade_signals").document(str(signal.id)).set(trade_signal_to_document(signal), merge=True)
        return signal

    def list_open_trades(self) -> list[TradeSignal]:
        return [
            trade_signal_from_document(snapshot.to_dict())
            for snapshot in self.collection("trade_signals").where("status", "==", "OPEN").stream()
        ]

    def list_closed_trades(self) -> list[TradeSignal]:
        return [
            trade_signal_from_document(snapshot.to_dict())
            for snapshot in self.collection("trade_signals").where("status", "==", "CLOSED").stream()
        ]

    def list_closed_trades_between(self, start_local: datetime, end_local: datetime) -> list[TradeSignal]:
        return [
            trade
            for trade in self.list_closed_trades()
            if trade.close_time is not None and start_local <= trade.close_time < end_local
        ]

    def upsert_strategy_insight(self, insight: StrategyInsight) -> StrategyInsight:
        if insight.id is None:
            insight.id = insight.trade_signal_id
        self.collection("strategy_insights").document(str(insight.trade_signal_id)).set(
            strategy_insight_to_document(insight),
            merge=True,
        )
        return insight

    def upsert_daily_summary(self, summary: DailySummary) -> DailySummary:
        if summary.id is None:
            summary.id = self.next_id("daily_summary_id")
        self.collection("daily_summaries").document(summary.summary_date.isoformat()).set(
            daily_summary_to_document(summary),
            merge=True,
        )
        return summary


def get_storage() -> TradeStorage:
    if settings.database_backend == "firestore":
        return FirestoreStorage()
    return SqlStorage()
