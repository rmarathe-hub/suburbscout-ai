"""Phase 8.5 — dynamic town-to-town commute lookup with JSON cache + Google Distance Matrix."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

import requests

from app import config
from app.config import COMMUTE_CACHE_PATH, COMMUTE_DESTINATION, GOOGLE_MAPS_API_KEY
from app.suburb_store import load_suburbs
from app.town_normalizer import canonical_town_name, normalize_key, resolve_town_in_dataset

DISTANCE_MATRIX_URL = "https://maps.googleapis.com/maps/api/distancematrix/json"
MAX_PAIRS_PER_REQUEST = 200
BOSTON_LABEL = "Boston / South Station"


@dataclass(frozen=True)
class CommuteResult:
    origin_town: str
    destination_town: str
    drive_minutes: float | None
    drive_miles: float | None
    source: str
    error: str | None = None
    cached: bool = False


def dynamic_commute_available() -> bool:
    return bool(GOOGLE_MAPS_API_KEY)


def is_boston_destination(destination_town: str | None) -> bool:
    if not destination_town:
        return True
    key = normalize_key(canonical_town_name(destination_town))
    return key in {"boston", "south station", "downtown boston"}


def commute_destination_label(destination_town: str | None) -> str:
    if is_boston_destination(destination_town):
        return BOSTON_LABEL
    return canonical_town_name(destination_town or "")


def _destination_address(destination_town: str) -> str:
    if is_boston_destination(destination_town):
        return COMMUTE_DESTINATION
    return f"{canonical_town_name(destination_town)}, MA"


def _origin_address(origin_town: str) -> str:
    return f"{canonical_town_name(origin_town)}, MA"


def _cache_key(origin_town: str, destination_town: str) -> str:
    return f"{canonical_town_name(origin_town)}|{_destination_address(destination_town)}"


def _load_cache() -> dict[str, Any]:
    if COMMUTE_CACHE_PATH.exists():
        with open(COMMUTE_CACHE_PATH, encoding="utf-8") as handle:
            return json.load(handle)
    return {}


def _save_cache(cache: dict[str, Any]) -> None:
    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with open(COMMUTE_CACHE_PATH, "w", encoding="utf-8") as handle:
        json.dump(cache, handle, indent=2)


def _boston_minutes_from_suburbs(origin_town: str) -> CommuteResult | None:
    key = normalize_key(canonical_town_name(origin_town))
    for suburb in load_suburbs():
        if normalize_key(suburb.get("name", "")) == key:
            minutes = suburb.get("drive_minutes_to_boston")
            miles = suburb.get("drive_distance_miles_to_boston")
            if minutes is None:
                return None
            return CommuteResult(
                origin_town=canonical_town_name(origin_town),
                destination_town=BOSTON_LABEL,
                drive_minutes=float(minutes),
                drive_miles=float(miles) if miles is not None else None,
                source="suburbs_json",
                cached=True,
            )
    return None


def _fetch_google_commute(origin_town: str, destination_town: str) -> dict[str, Any]:
    origin = _origin_address(origin_town)
    destination = _destination_address(destination_town)
    fetched_at = datetime.now(timezone.utc).isoformat()
    params = {
        "origins": origin,
        "destinations": destination,
        "mode": "driving",
        "key": GOOGLE_MAPS_API_KEY,
    }
    try:
        response = requests.get(DISTANCE_MATRIX_URL, params=params, timeout=30)
        data = response.json()
    except requests.RequestException as exc:
        return {
            "town": canonical_town_name(origin_town),
            "origin": origin,
            "destination": destination,
            "destination_town": canonical_town_name(destination_town),
            "drive_minutes": None,
            "drive_miles": None,
            "google_status": "REQUEST_ERROR",
            "element_status": str(exc),
            "source": "google_distance_matrix",
            "fetched_at": fetched_at,
            "error": str(exc),
        }

    drive_minutes = None
    drive_miles = None
    element_status = None
    rows = data.get("rows") or []
    if rows and rows[0].get("elements"):
        element = rows[0]["elements"][0]
        element_status = element.get("status")
        if element_status == "OK":
            duration_sec = element.get("duration", {}).get("value")
            distance_m = element.get("distance", {}).get("value")
            if duration_sec is not None:
                drive_minutes = round(duration_sec / 60, 1)
            if distance_m is not None:
                drive_miles = round(distance_m / 1609.34, 2)

    return {
        "town": canonical_town_name(origin_town),
        "origin": origin,
        "destination": destination,
        "destination_town": canonical_town_name(destination_town),
        "drive_minutes": drive_minutes,
        "drive_miles": drive_miles,
        "google_status": data.get("status", "UNKNOWN"),
        "element_status": element_status,
        "source": "google_distance_matrix",
        "fetched_at": fetched_at,
    }


def _record_from_cache(raw: dict[str, Any], *, origin_town: str, destination_town: str) -> CommuteResult:
    return CommuteResult(
        origin_town=canonical_town_name(origin_town),
        destination_town=commute_destination_label(destination_town),
        drive_minutes=raw.get("drive_minutes"),
        drive_miles=raw.get("drive_miles"),
        source=str(raw.get("source") or "cache"),
        error=raw.get("error"),
        cached=True,
    )


def get_commute_minutes(origin_town: str, destination_town: str) -> CommuteResult:
    """Return drive time for one origin→destination pair (cache-first, one Google call on miss)."""
    origin = canonical_town_name(origin_town)
    destination = canonical_town_name(destination_town)

    if is_boston_destination(destination):
        stored = _boston_minutes_from_suburbs(origin)
        if stored:
            return stored
        return CommuteResult(
            origin_town=origin,
            destination_town=BOSTON_LABEL,
            drive_minutes=None,
            drive_miles=None,
            source="suburbs_json",
            error="Boston commute not available for this town in suburbs.json",
        )

    cache = _load_cache()
    key = _cache_key(origin, destination)
    if key in cache:
        return _record_from_cache(cache[key], origin_town=origin, destination_town=destination)

    if not dynamic_commute_available():
        return CommuteResult(
            origin_town=origin,
            destination_town=commute_destination_label(destination),
            drive_minutes=None,
            drive_miles=None,
            source="unavailable",
            error="GOOGLE_MAPS_API_KEY is not configured",
        )

    record = _fetch_google_commute(origin, destination)
    cache[key] = record
    _save_cache(cache)
    time.sleep(0.05)
    return _record_from_cache(record, origin_town=origin, destination_town=destination)


def ensure_destination_matrix(
    destination_town: str,
    origin_towns: list[str] | None = None,
) -> dict[str, float | None]:
    """
    Build origin→minutes map for ranking. Fetches only missing cache entries.
    At most MAX_PAIRS_PER_REQUEST origins per call.
    """
    if is_boston_destination(destination_town):
        suburbs = load_suburbs()
        origins = origin_towns or [s["name"] for s in suburbs]
        matrix: dict[str, float | None] = {}
        for name in origins[:MAX_PAIRS_PER_REQUEST]:
            suburb = _suburb_by_name(name, suburbs)
            minutes = suburb.get("drive_minutes_to_boston") if suburb else None
            matrix[canonical_town_name(name)] = float(minutes) if minutes is not None else None
        return matrix

    suburbs = load_suburbs()
    origins = origin_towns or [s["name"] for s in suburbs]
    origins = [canonical_town_name(t) for t in origins[:MAX_PAIRS_PER_REQUEST]]

    matrix: dict[str, float | None] = {}
    fetches = 0
    for origin in origins:
        if normalize_key(origin) == normalize_key(destination_town):
            matrix[origin] = 0.0
            continue
        result = get_commute_minutes(origin, destination_town)
        matrix[origin] = result.drive_minutes
        if not result.cached and result.source == "google_distance_matrix":
            fetches += 1
        if fetches >= MAX_PAIRS_PER_REQUEST:
            break
    return matrix


def _suburb_by_name(name: str, suburbs: list[dict[str, Any]]) -> dict[str, Any] | None:
    key = normalize_key(canonical_town_name(name))
    for suburb in suburbs:
        if normalize_key(suburb.get("name", "")) == key:
            return suburb
    return None


@lru_cache(maxsize=1)
def dataset_town_names() -> tuple[str, ...]:
    return tuple(s["name"] for s in load_suburbs())


def resolve_dataset_town(name: str) -> str | None:
    return resolve_town_in_dataset(name, list(dataset_town_names()))
