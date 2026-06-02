#!/usr/bin/env python3
"""Fetch and cache Google Distance Matrix commute times for suburb list towns."""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.config import (  # noqa: E402
    COMMUTE_CACHE_PATH,
    COMMUTE_CSV_PATH,
    COMMUTE_DESTINATION,
    GOOGLE_MAPS_API_KEY,
    PROCESSED_DIR,
)
from app.data_loader import load_suburb_list  # noqa: E402

DISTANCE_MATRIX_URL = "https://maps.googleapis.com/maps/api/distancematrix/json"


def load_cache() -> dict:
    if COMMUTE_CACHE_PATH.exists():
        with open(COMMUTE_CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cache(cache: dict) -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with open(COMMUTE_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)


def fetch_commute(origin_town: str, destination: str, api_key: str) -> dict:
    origin = f"{origin_town}, MA"
    params = {
        "origins": origin,
        "destinations": destination,
        "mode": "driving",
        "key": api_key,
    }
    fetched_at = datetime.now(timezone.utc).isoformat()
    try:
        resp = requests.get(DISTANCE_MATRIX_URL, params=params, timeout=30)
        data = resp.json()
    except requests.RequestException as exc:
        return {
            "town": origin_town,
            "origin": origin,
            "destination": destination,
            "drive_minutes_to_boston": None,
            "drive_distance_miles_to_boston": None,
            "google_status": "REQUEST_ERROR",
            "element_status": str(exc),
            "source": "google_distance_matrix",
            "fetched_at": fetched_at,
            "error": str(exc),
        }

    google_status = data.get("status", "UNKNOWN")
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
        "town": origin_town,
        "origin": origin,
        "destination": destination,
        "drive_minutes_to_boston": drive_minutes,
        "drive_distance_miles_to_boston": drive_miles,
        "google_status": google_status,
        "element_status": element_status,
        "source": "google_distance_matrix",
        "fetched_at": fetched_at,
    }


def main() -> None:
    if not GOOGLE_MAPS_API_KEY:
        raise SystemExit("GOOGLE_MAPS_API_KEY is not set in .env")

    suburb_df = load_suburb_list()
    towns = suburb_df["town"].tolist()
    cache = load_cache()
    destination = COMMUTE_DESTINATION

    results = []
    fetched_count = 0
    cached_count = 0

    for i, town in enumerate(towns):
        cache_key = f"{town}|{destination}"
        if cache_key in cache:
            results.append(cache[cache_key])
            cached_count += 1
            continue

        print(f"[{i + 1}/{len(towns)}] Fetching commute for {town}...")
        record = fetch_commute(town, destination, GOOGLE_MAPS_API_KEY)
        cache[cache_key] = record
        results.append(record)
        fetched_count += 1
        save_cache(cache)
        time.sleep(0.15)  # gentle rate limit

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(results).to_csv(COMMUTE_CSV_PATH, index=False)

    ok = sum(1 for r in results if r.get("drive_minutes_to_boston") is not None)
    print(f"Wrote {COMMUTE_CSV_PATH}")
    print(f"  cached: {cached_count}, newly fetched: {fetched_count}, with drive time: {ok}/{len(towns)}")


if __name__ == "__main__":
    main()
