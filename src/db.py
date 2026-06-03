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
        connection.execute(text("CREATE TABLE IF NOT EXISTS app_metadata (key TEXT PRIMARY KEY, value TEXT)"))
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

        migration_key = "timezone_migrated_to_asia_bangkok_v1"
        migrated = connection.execute(
            text("SELECT value FROM app_metadata WHERE key = :key"),
            {"key": migration_key},
        ).scalar_one_or_none()
        if migrated == "done":
            return

        if dialect == "sqlite":
            connection.execute(text("UPDATE trade_signals SET signal_time = datetime(signal_time, '+7 hours') WHERE signal_time IS NOT NULL"))
            connection.execute(text("UPDATE trade_signals SET close_time = datetime(close_time, '+7 hours') WHERE close_time IS NOT NULL"))
            connection.execute(text("UPDATE trade_signals SET created_at = datetime(created_at, '+7 hours') WHERE created_at IS NOT NULL"))
            connection.execute(text("UPDATE trade_signals SET updated_at = datetime(updated_at, '+7 hours') WHERE updated_at IS NOT NULL"))
            connection.execute(text("UPDATE daily_summaries SET created_at = datetime(created_at, '+7 hours') WHERE created_at IS NOT NULL"))
            connection.execute(text("UPDATE strategy_insights SET generated_at = datetime(generated_at, '+7 hours') WHERE generated_at IS NOT NULL"))
        elif dialect == "postgresql":
            connection.execute(text("UPDATE trade_signals SET signal_time = signal_time + INTERVAL '7 hours' WHERE signal_time IS NOT NULL"))
            connection.execute(text("UPDATE trade_signals SET close_time = close_time + INTERVAL '7 hours' WHERE close_time IS NOT NULL"))
            connection.execute(text("UPDATE trade_signals SET created_at = created_at + INTERVAL '7 hours' WHERE created_at IS NOT NULL"))
            connection.execute(text("UPDATE trade_signals SET updated_at = updated_at + INTERVAL '7 hours' WHERE updated_at IS NOT NULL"))
            connection.execute(text("UPDATE daily_summaries SET created_at = created_at + INTERVAL '7 hours' WHERE created_at IS NOT NULL"))
            connection.execute(text("UPDATE strategy_insights SET generated_at = generated_at + INTERVAL '7 hours' WHERE generated_at IS NOT NULL"))

        connection.execute(
            text("INSERT OR REPLACE INTO app_metadata(key, value) VALUES (:key, 'done')") if dialect == "sqlite"
            else text(
                "INSERT INTO app_metadata(key, value) VALUES (:key, 'done') "
                "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"
            ),
            {"key": migration_key},
        )
