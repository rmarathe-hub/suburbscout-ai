#!/usr/bin/env python3
"""Build merged suburbs.json from raw datasets and suburb_list.csv."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.config import (  # noqa: E402
    COMMUTE_CSV_PATH,
    CORE_FIELDS,
    PROCESSED_DIR,
    SUBURBS_CLEAN_CSV_PATH,
    SUBURBS_JSON_PATH,
)
from app.data_loader import (  # noqa: E402
    load_commute_times,
    load_crime_data,
    load_dor_data,
    load_housing_prices,
    load_school_scores,
    load_suburb_list,
    lookup_by_town_key,
    lookup_crime_for_town,
)
from app.geo_enrichment import apply_geo_enrichment  # noqa: E402
from app.town_normalizer import normalize_key  # noqa: E402


def percentile_score(series: pd.Series, higher_is_better: bool = True) -> pd.Series:
    """Map values to 0-10 percentile scores. NaN stays NaN."""
    valid = series.dropna()
    if valid.empty:
        return pd.Series([np.nan] * len(series), index=series.index)

    # Rank so the best raw values get the highest rank (then mapped to ~10).
    ranks = valid.rank(method="average", ascending=higher_is_better)
    pct = (ranks - 1) / max(len(valid) - 1, 1) * 10
    out = pd.Series(np.nan, index=series.index, dtype=float)
    out.loc[valid.index] = pct.round(2)
    return out


def build_suburbs_records() -> list[dict]:
    suburb_df = load_suburb_list()
    towns = suburb_df["town"].tolist()
    region_map = dict(zip(suburb_df["town"], suburb_df["region"]))

    housing_df = load_housing_prices()
    dor_df = load_dor_data()
    crime_df = load_crime_data()
    school_df = load_school_scores()
    commute_df = load_commute_times(COMMUTE_CSV_PATH)

    records: list[dict] = []
    for town in towns:
        missing: list[str] = []
        sources: list[str] = []

        row: dict = {
            "name": town,
            "region": region_map.get(town, ""),
            "county": None,
            "population": None,
            "latest_home_price": None,
            "home_price_year": None,
            "dor_income_per_capita": None,
            "eqv_per_capita": None,
            "economic_score": None,
            "crime_actual_offenses": None,
            "crime_rate_per_1000": None,
            "safety_score": None,
            "drive_minutes_to_boston": None,
            "drive_distance_miles_to_boston": None,
            "commute_score": None,
            "school_score": None,
            "affordability_score": None,
            "family_score": None,
            "missing_fields": missing,
            "data_sources": sources,
            "tags": [],
            "data_quality_tier": "partial",
        }

        # Housing
        h = lookup_by_town_key(housing_df, town)
        if h is not None:
            row["latest_home_price"] = int(h["latest_home_price"]) if pd.notna(h["latest_home_price"]) else None
            row["home_price_year"] = int(h["home_price_year"]) if pd.notna(h["home_price_year"]) else None
            if row["county"] is None and pd.notna(h.get("housing_county")):
                row["county"] = str(h["housing_county"]).title()
            sources.append("housing_price_data.txt")
        else:
            missing.extend(["latest_home_price", "home_price_year"])

        # DOR
        d = lookup_by_town_key(dor_df, town)
        if d is not None:
            row["population"] = int(d["population"]) if pd.notna(d["population"]) else None
            row["dor_income_per_capita"] = (
                int(d["dor_income_per_capita"]) if pd.notna(d["dor_income_per_capita"]) else None
            )
            row["eqv_per_capita"] = int(d["eqv_per_capita"]) if pd.notna(d["eqv_per_capita"]) else None
            if row["county"] is None and pd.notna(d.get("county")):
                row["county"] = str(d["county"]).title()
            sources.append("DOR_Income_EQV_Per_Capita.xlsx")
        else:
            missing.extend(["population", "dor_income_per_capita", "eqv_per_capita"])

        # Crime
        c = lookup_crime_for_town(crime_df, town, towns)
        if c is not None:
            row["crime_actual_offenses"] = (
                int(c["crime_actual_offenses"]) if pd.notna(c["crime_actual_offenses"]) else None
            )
            row["crime_rate_per_1000"] = (
                float(c["crime_rate_per_1000"]) if pd.notna(c["crime_rate_per_1000"]) else None
            )
            sources.append("SRS Crime Rates CSV")
        else:
            missing.extend(["crime_actual_offenses", "crime_rate_per_1000", "safety_score"])

        # Schools
        s = lookup_by_town_key(school_df, town)
        school_raw = None
        if s is not None and pd.notna(s.get("school_score_raw")):
            school_raw = float(s["school_score_raw"])
            sources.append("MA_Public_Schools_2017.csv")
        else:
            district_rows = school_df[school_df["district_key"] == normalize_key(town)]
            if not district_rows.empty and pd.notna(district_rows.iloc[0].get("district_school_score")):
                school_raw = float(district_rows.iloc[0]["district_school_score"])
                sources.append("MA_Public_Schools_2017.csv (district rollup)")
        if school_raw is not None:
            row["_school_score_raw"] = school_raw
        else:
            missing.append("school_score")

        # Commute
        cm = lookup_by_town_key(commute_df, town)
        if cm is not None and pd.notna(cm.get("drive_minutes_to_boston")):
            row["drive_minutes_to_boston"] = float(cm["drive_minutes_to_boston"])
            dist = cm.get("drive_distance_miles_to_boston")
            row["drive_distance_miles_to_boston"] = float(dist) if pd.notna(dist) else None
            sources.append("Google Distance Matrix")
        else:
            missing.extend(
                ["drive_minutes_to_boston", "drive_distance_miles_to_boston", "commute_score"]
            )

        row["missing_fields"] = sorted(set(missing))
        row["data_sources"] = sorted(set(sources))
        records.append(row)

    df = pd.DataFrame(records)

    # Percentile-based scores across suburb list
    df["school_score"] = percentile_score(
        df.get("_school_score_raw", pd.Series(dtype=float)), higher_is_better=True
    )
    df["safety_score"] = percentile_score(
        df["crime_rate_per_1000"].astype(float), higher_is_better=False
    )
    df["commute_score"] = percentile_score(
        df["drive_minutes_to_boston"].astype(float), higher_is_better=False
    )
    df["affordability_score"] = percentile_score(
        df["latest_home_price"].astype(float), higher_is_better=False
    )

    # Economic: average percentile of income and EQV
    income_pct = percentile_score(df["dor_income_per_capita"].astype(float), higher_is_better=True)
    eqv_pct = percentile_score(df["eqv_per_capita"].astype(float), higher_is_better=True)
    df["economic_score"] = ((income_pct + eqv_pct) / 2).round(2)

    # Family score: mean of available family-related scores
    family_cols = ["school_score", "safety_score", "affordability_score", "economic_score"]
    df["family_score"] = df[family_cols].mean(axis=1, skipna=True).round(2)

    # Phase 1.1: curated coastal flag + region_key slug (before tags)
    geo_rows = [apply_geo_enrichment(r) for r in df.to_dict(orient="records")]
    df = pd.DataFrame(geo_rows)

    # Tags from region + coastal + score hints
    def make_tags(r) -> list[str]:
        tags = []
        if r.get("region"):
            tags.append(r["region"])
        if r.get("is_coastal"):
            tags.append("coastal")
        for label, col, threshold in [
            ("strong schools", "school_score", 7.0),
            ("low crime", "safety_score", 7.0),
            ("short commute", "commute_score", 7.0),
            ("more affordable", "affordability_score", 7.0),
            ("higher income area", "economic_score", 7.0),
            ("family-friendly", "family_score", 7.0),
        ]:
            val = r.get(col)
            if val is not None and not pd.isna(val) and float(val) >= threshold:
                tags.append(label)
        return tags

    df["tags"] = df.apply(make_tags, axis=1)

    # Data quality tier
    def tier(r) -> str:
        for field in CORE_FIELDS:
            val = r.get(field)
            if val is None or (isinstance(val, float) and pd.isna(val)):
                return "partial"
        return "full"

    df["data_quality_tier"] = df.apply(tier, axis=1)

    if "_school_score_raw" in df.columns:
        df = df.drop(columns=["_school_score_raw"])

    # Replace NaN with None for JSON
    output = []
    for _, r in df.iterrows():
        item = {}
        for col, val in r.items():
            if isinstance(val, float) and pd.isna(val):
                item[col] = None
            elif isinstance(val, (np.integer,)):
                item[col] = int(val)
            elif isinstance(val, (np.floating,)):
                item[col] = float(val) if not pd.isna(val) else None
            else:
                item[col] = val
        output.append(item)
    return output


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    records = build_suburbs_records()
    SUBURBS_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(SUBURBS_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)

    pd.DataFrame(records).to_csv(SUBURBS_CLEAN_CSV_PATH, index=False)

    full = sum(1 for r in records if r["data_quality_tier"] == "full")
    coastal = sum(1 for r in records if r.get("is_coastal"))
    print(f"Wrote {len(records)} towns to {SUBURBS_JSON_PATH}")
    print(f"  full data tier: {full}")
    print(f"  partial data tier: {len(records) - full}")
    print(f"  coastal (curated): {coastal}")
    print(f"Wrote {SUBURBS_CLEAN_CSV_PATH}")


if __name__ == "__main__":
    main()
