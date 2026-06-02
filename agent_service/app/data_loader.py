"""Load raw datasets and suburb list for the data pipeline."""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from app.config import (
    CRIME_FILE,
    DOR_FILE,
    HOUSING_FILE,
    SCHOOLS_FILE,
    SUBURB_LIST_PATH,
)
from app.town_normalizer import find_canonical_in_set, normalize_key, town_match_keys

# Jurisdiction labels that are not municipal police departments
CRIME_SKIP_PATTERNS = (
    r"^massachusetts$",
    r"state police",
    r"transit police",
    r"college",
    r"university",
    r"hospital",
    r"campus",
    r" sheriff",
    r"^jurisdiction",
    r"^measures$",
)

# MCAS columns used for school score (HS preferred, then MS)
SCHOOL_MCAS_PCT_COLUMNS = [
    "% MCAS_10thGrade_Math_P+A",
    "% MCAS_10thGrade_English_P+A",
    "% MCAS_8thGrade_Math_P+A",
    "% MCAS_8thGrade_English_P+A",
    "% Graduated",
]


def load_suburb_list(path: Path | None = None) -> pd.DataFrame:
    """Load suburb_list.csv with region and town columns."""
    path = path or SUBURB_LIST_PATH
    df = pd.read_csv(path)
    if "town" not in df.columns:
        raise ValueError(f"{path} must include a 'town' column")
    df["town"] = df["town"].astype(str).str.strip()
    if "region" not in df.columns:
        df["region"] = ""
    return df.drop_duplicates(subset=["town"]).reset_index(drop=True)


def _parse_numeric(value) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    if not text or text.upper() in {"NA", "N/A", "NULL", "-"}:
        return None
    text = text.replace(",", "")
    try:
        return float(text)
    except ValueError:
        return None


def load_housing_prices(path: Path | None = None) -> pd.DataFrame:
    """Latest house_price per town (newest year)."""
    path = path or HOUSING_FILE
    df = pd.read_csv(path, sep="\t")
    df = df[df["cat"] == "house_price"].copy()
    df["value"] = df["value"].apply(_parse_numeric)
    df = df.dropna(subset=["value"])
    df["town_key"] = df["town"].astype(str).map(normalize_key)
    df = df.sort_values(["town_key", "year"], ascending=[True, False])
    latest = df.groupby("town_key", as_index=False).first()
    return latest.rename(
        columns={
            "town": "housing_town",
            "value": "latest_home_price",
            "year": "home_price_year",
            "county": "housing_county",
        }
    )


def load_dor_data(path: Path | None = None) -> pd.DataFrame:
    """DOR income and EQV per capita by municipality."""
    path = path or DOR_FILE
    df = pd.read_excel(path)
    df.columns = [str(c).strip() for c in df.columns]
    rename = {
        "Municipality": "dor_town",
        "County": "county",
        "Population": "population",
        "DOR Income Per Capita": "dor_income_per_capita",
        "EQV Per Capita": "eqv_per_capita",
    }
    df = df.rename(columns=rename)
    df["town_key"] = df["dor_town"].astype(str).map(normalize_key)
    for col in ("population", "dor_income_per_capita", "eqv_per_capita"):
        df[col] = df[col].apply(_parse_numeric)
    return df


def _is_municipal_crime_jurisdiction(name: str) -> bool:
    lower = name.strip().lower()
    for pattern in CRIME_SKIP_PATTERNS:
        if re.search(pattern, lower):
            return False
    return bool(lower)


def load_crime_data(path: Path | None = None) -> pd.DataFrame:
    """Crime rates by municipal jurisdiction."""
    path = path or CRIME_FILE
    rows: list[dict] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            match = re.match(
                r'^"([^"]+)","([^"]*)","([^"]*)","([^"]*)"\s*,?\s*$', line
            )
            if not match:
                continue
            jurisdiction, offenses, population, rate = match.groups()
            if not _is_municipal_crime_jurisdiction(jurisdiction):
                continue
            rows.append(
                {
                    "crime_jurisdiction": jurisdiction.strip(),
                    "crime_actual_offenses": _parse_numeric(offenses),
                    "crime_population": _parse_numeric(population),
                    "crime_rate_per_1000": _parse_numeric(rate),
                    "town_key": normalize_key(jurisdiction),
                }
            )
    return pd.DataFrame(rows)


def _school_numeric_columns(df: pd.DataFrame) -> list[str]:
    cols = [c for c in SCHOOL_MCAS_PCT_COLUMNS if c in df.columns]
    return cols


def load_school_scores(path: Path | None = None) -> pd.DataFrame:
    """
    Town-level school score from median MCAS % P+A and graduation where available.
    Falls back to district-level rollup when town has no rows.
    """
    path = path or SCHOOLS_FILE
    df = pd.read_csv(path, low_memory=False)
    mcas_cols = _school_numeric_columns(df)
    if not mcas_cols:
        return pd.DataFrame(columns=["town_key", "school_score_raw", "school_metric_count"])

    for col in mcas_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    def row_score(row) -> float | None:
        values = [row[c] for c in mcas_cols if pd.notna(row[c])]
        if not values:
            return None
        return float(sum(values) / len(values))

    df["school_row_score"] = df.apply(row_score, axis=1)
    df["town_key"] = df["Town"].astype(str).map(normalize_key)

    town_scores = (
        df.dropna(subset=["school_row_score"])
        .groupby("town_key", as_index=False)
        .agg(
            school_score_raw=("school_row_score", "median"),
            school_metric_count=("school_row_score", "count"),
        )
    )

    # District rollup for towns missing direct school rows
    df["district_key"] = df["District Name"].astype(str).map(normalize_key)
    district_scores = (
        df.dropna(subset=["school_row_score"])
        .groupby("district_key", as_index=False)
        .agg(district_school_score=("school_row_score", "median"))
    )
    town_scores = town_scores.merge(
        district_scores,
        left_on="town_key",
        right_on="district_key",
        how="left",
    )
    return town_scores


def load_commute_times(path: Path) -> pd.DataFrame:
    """Load processed commute CSV if it exists."""
    columns = [
        "town",
        "drive_minutes_to_boston",
        "drive_distance_miles_to_boston",
    ]
    if not path.exists():
        return pd.DataFrame(columns=[*columns, "town_key"])
    df = pd.read_csv(path)
    df["town_key"] = df["town"].astype(str).map(normalize_key)
    return df


def lookup_by_town_key(df: pd.DataFrame, town: str, key_col: str = "town_key") -> pd.Series | None:
    """Return first row matching any alias key for a display town name."""
    keys = town_match_keys(town)
    matches = df[df[key_col].isin(keys)]
    if matches.empty:
        return None
    return matches.iloc[0]


def lookup_crime_for_town(crime_df: pd.DataFrame, town: str, all_towns: list[str]) -> pd.Series | None:
    """Match crime row to town, trying jurisdiction name resolution."""
    row = lookup_by_town_key(crime_df, town)
    if row is not None:
        return row
    # Exact jurisdiction name match among known towns
    for _, crow in crime_df.iterrows():
        canonical = find_canonical_in_set(crow["crime_jurisdiction"], all_towns)
        if canonical == town:
            return crow
    return None
