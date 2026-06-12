"""Suburb reference data — Postgres (Phase 3C) with suburbs.json fallback."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.config import SUBURBS_JSON_PATH
from app.db import db_available, db_configured, get_db_session
from app.db_models import Suburb

logger = logging.getLogger(__name__)

_cache: list[dict[str, Any]] | None = None
_cache_source: str | None = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def clear_suburbs_cache() -> None:
    """Drop in-memory suburb list (call after seed/upsert or in tests)."""
    global _cache, _cache_source
    _cache = None
    _cache_source = None
    for mod_attr in (
        ("app.entity_extractor", "_dataset_towns"),
        ("app.constraint_parser", "_known_towns_by_length"),
        ("app.constraint_parser", "_known_town_keys"),
        ("app.query_patterns", "_dataset_towns"),
    ):
        try:
            import importlib

            mod = importlib.import_module(mod_attr[0])
            fn = getattr(mod, mod_attr[1])
            fn.cache_clear()
        except Exception:
            pass


def suburbs_table_count() -> int:
    """Return row count in suburbs table, or 0 when DB is unavailable."""
    if not db_configured() or not db_available():
        return 0
    try:
        with get_db_session() as db:
            count = db.scalar(select(func.count()).select_from(Suburb))
            return int(count or 0)
    except Exception:
        logger.debug("suburbs_table_count failed", exc_info=True)
        return 0


def suburbs_dataset_available() -> bool:
    """True when suburb data is loadable from Postgres or suburbs.json."""
    if suburbs_table_count() > 0:
        return True
    return SUBURBS_JSON_PATH.is_file()


def suburbs_data_source() -> str:
    """Human-readable source label for tool/API metadata."""
    if _cache_source:
        return _cache_source
    if suburbs_table_count() > 0:
        return "postgres:suburbs"
    if SUBURBS_JSON_PATH.is_file():
        return SUBURBS_JSON_PATH.name
    return "unavailable"


def _load_suburbs_from_file(path: Path) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a JSON array of suburb records")
    return data


def _load_suburbs_from_db() -> list[dict[str, Any]]:
    with get_db_session() as db:
        rows = db.scalars(select(Suburb).order_by(Suburb.name)).all()
        return [dict(row.data) for row in rows]


def load_suburbs(path: Path | None = None) -> list[dict[str, Any]]:
    """Load curated suburb records — Postgres when seeded, else suburbs.json."""
    global _cache, _cache_source

    if path is not None:
        return _load_suburbs_from_file(path)

    if _cache is not None:
        return _cache

    if db_configured() and db_available() and suburbs_table_count() > 0:
        try:
            suburbs = _load_suburbs_from_db()
            _cache = suburbs
            _cache_source = "postgres:suburbs"
            return suburbs
        except Exception:
            logger.warning("postgres suburb load failed; falling back to JSON", exc_info=True)

    if not SUBURBS_JSON_PATH.is_file():
        raise FileNotFoundError(
            f"Suburb dataset missing: no Postgres rows and {SUBURBS_JSON_PATH} not found. "
            "Run scripts/build_suburbs_dataset.py and scripts/seed_suburbs.py"
        )

    suburbs = _load_suburbs_from_file(SUBURBS_JSON_PATH)
    _cache = suburbs
    _cache_source = SUBURBS_JSON_PATH.name
    return suburbs


def upsert_suburbs(records: list[dict[str, Any]]) -> int:
    """Insert or update suburb rows from build/seed pipeline."""
    if not records:
        return 0
    if not db_configured():
        logger.debug("upsert_suburbs skipped — DATABASE_URL not set")
        return 0

    now = _utcnow()
    values = []
    for record in records:
        name = str(record.get("name") or "").strip()
        if not name:
            continue
        values.append({"name": name, "data": record, "updated_at": now})

    if not values:
        return 0

    with get_db_session() as db:
        stmt = insert(Suburb).values(values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["name"],
            set_={"data": stmt.excluded.data, "updated_at": stmt.excluded.updated_at},
        )
        db.execute(stmt)

    clear_suburbs_cache()
    return len(values)


def seed_suburbs_from_json(path: Path | None = None) -> int:
    """Load suburbs.json (or path) into Postgres."""
    json_path = path or SUBURBS_JSON_PATH
    if not json_path.is_file():
        raise FileNotFoundError(f"Missing {json_path} — run scripts/build_suburbs_dataset.py first")
    records = _load_suburbs_from_file(json_path)
    return upsert_suburbs(records)
