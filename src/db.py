from __future__ import annotations

from sqlalchemy import create_engine
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
