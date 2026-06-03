from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.db import Base
from src.time_utils import local_now_naive


class TradeSignal(Base):
    __tablename__ = "trade_signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    timeframe: Mapped[str] = mapped_column(String(10))
    side: Mapped[str] = mapped_column(String(10), index=True)
    status: Mapped[str] = mapped_column(String(20), index=True, default="OPEN")
    bias: Mapped[str] = mapped_column(String(10))
    strategy_version: Mapped[str] = mapped_column(String(20), default="v1")
    signal_time: Mapped[datetime] = mapped_column(DateTime, index=True)
    entry_price: Mapped[float] = mapped_column(Float)
    stop_loss: Mapped[float] = mapped_column(Float)
    take_profit: Mapped[float] = mapped_column(Float)
    risk_reward: Mapped[float] = mapped_column(Float)
    signal_score: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text)
    setup_json: Mapped[str] = mapped_column(Text)
    close_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    close_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    pnl_r: Mapped[float | None] = mapped_column(Float, nullable=True)
    telegram_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=local_now_naive)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=local_now_naive, onupdate=local_now_naive)


class DailySummary(Base):
    __tablename__ = "daily_summaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    summary_date: Mapped[datetime.date] = mapped_column(Date, unique=True, index=True)
    total_trades: Mapped[int] = mapped_column(Integer)
    wins: Mapped[int] = mapped_column(Integer)
    losses: Mapped[int] = mapped_column(Integer)
    winrate: Mapped[float] = mapped_column(Float)
    total_r: Mapped[float] = mapped_column(Float)
    notes: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=local_now_naive)


class StrategyInsight(Base):
    __tablename__ = "strategy_insights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trade_signal_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=local_now_naive, index=True)
    scope: Mapped[str] = mapped_column(String(30), index=True, default="rolling_30")
    winrate: Mapped[float] = mapped_column(Float)
    total_trades: Mapped[int] = mapped_column(Integer)
    recommendation: Mapped[str] = mapped_column(Text)
