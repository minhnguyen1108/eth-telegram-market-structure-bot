from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy import text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from src.config import settings


class Base(DeclarativeBase):
    pass


def normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql://") and "+psycopg" not in database_url:
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


engine = create_engine(normalize_database_url(settings.database_url), future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def ensure_schema_updates() -> None:
    with engine.begin() as connection:
        dialect = connection.dialect.name
        if dialect == "sqlite":
            columns = {row[1] for row in connection.execute(text("PRAGMA table_info(strategy_insights)"))}
            if "trade_signal_id" not in columns:
                try:
                    connection.execute(text("ALTER TABLE strategy_insights ADD COLUMN trade_signal_id INTEGER"))
                except Exception:
                    pass
            connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_strategy_insights_trade_signal_id ON strategy_insights(trade_signal_id)"))
        elif dialect == "postgresql":
            connection.execute(text("ALTER TABLE strategy_insights ADD COLUMN IF NOT EXISTS trade_signal_id INTEGER"))
            connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_strategy_insights_trade_signal_id ON strategy_insights(trade_signal_id)"))
