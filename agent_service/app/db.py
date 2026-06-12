"""Database engine and session helpers (Phase 3A)."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app import config

logger = logging.getLogger(__name__)

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def db_configured() -> bool:
    return bool(config.DATABASE_URL)


def _get_engine() -> Engine:
    global _engine, _SessionLocal
    if _engine is None:
        if not config.DATABASE_URL:
            raise RuntimeError("DATABASE_URL is not configured")
        _engine = create_engine(config.DATABASE_URL, pool_pre_ping=True)
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    return _engine


def db_available() -> bool:
    """Return True when DATABASE_URL is set and Postgres responds."""
    if not db_configured():
        return False
    try:
        with get_db_session() as session:
            session.execute(text("SELECT 1"))
        return True
    except Exception:
        logger.debug("database unavailable", exc_info=True)
        return False


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session; rolls back on error."""
    _get_engine()
    assert _SessionLocal is not None
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
