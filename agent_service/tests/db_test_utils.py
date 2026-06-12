"""Shared helpers for Postgres integration tests (Phase 3A)."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator


def reset_db_engine() -> None:
    """Clear cached SQLAlchemy engine after DATABASE_URL changes in tests."""
    import app.db as db_module

    db_module._engine = None
    db_module._SessionLocal = None


@contextmanager
def temporary_database_url(url: str | None) -> Generator[None, None, None]:
    """Temporarily override DATABASE_URL and reset the engine cache."""
    from app import config

    original = config.DATABASE_URL
    try:
        config.DATABASE_URL = url
        reset_db_engine()
        yield
    finally:
        config.DATABASE_URL = original
        reset_db_engine()


def postgres_integration_enabled() -> bool:
    """True when DATABASE_URL is set and Postgres responds."""
    try:
        from app.db import db_available, db_configured

        return db_configured() and db_available()
    except Exception:
        return False


def skip_unless_postgres(reason: str = "Postgres not available (set DATABASE_URL and run docker compose up -d)") -> str:
    return reason
