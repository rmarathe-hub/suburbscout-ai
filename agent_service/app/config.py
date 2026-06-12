"""Application configuration loaded from environment and fixed paths."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# agent_service/ (parent of app/)
SERVICE_ROOT = Path(__file__).resolve().parent.parent
APP_ROOT = Path(__file__).resolve().parent
DATA_DIR = APP_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
VECTOR_DIR = DATA_DIR / "vector_index"
VECTOR_EMBEDDINGS_PATH = VECTOR_DIR / "embeddings.npy"
VECTOR_METADATA_PATH = VECTOR_DIR / "metadata.json"
EMBEDDING_BATCH_SIZE = 32

COASTAL_TOWNS_PATH = DATA_DIR / "coastal_towns.csv"
SUBURB_LIST_PATH = DATA_DIR / "suburb_list.csv"
SUBURBS_JSON_PATH = DATA_DIR / "suburbs.json"
TOWN_PROFILES_PATH = DATA_DIR / "town_profiles.json"
COMMUTE_CSV_PATH = PROCESSED_DIR / "commute_times.csv"
COMMUTE_CACHE_PATH = PROCESSED_DIR / "commute_cache.json"
SUBURBS_CLEAN_CSV_PATH = PROCESSED_DIR / "suburbs_clean.csv"
SAVED_SEARCHES_PATH = APP_ROOT / "saved_searches.jsonl"
QUERY_AGENT_AUDIT_PATH = APP_ROOT / "query_agent_audit.jsonl"

# Raw source filenames (fixed names under RAW_DIR)
HOUSING_FILE = RAW_DIR / "housing_price_data.txt"
DOR_FILE = RAW_DIR / "DOR_Income_EQV_Per_Capita.xlsx"
CRIME_FILE = RAW_DIR / "SRS Crime Rates by Local Police Department (Ranked by Population).csv"
SCHOOLS_FILE = RAW_DIR / "MA_Public_Schools_2017.csv"

load_dotenv(SERVICE_ROOT / ".env")

# --- Phase 3A: PostgreSQL (optional — unset to skip DB persistence) ---
DATABASE_URL = os.getenv("DATABASE_URL", "").strip() or None

# --- Day 2: Agent (Foundry-first, OpenAI fallback) ---
FOUNDRY_PROJECT_ENDPOINT = os.getenv("FOUNDRY_PROJECT_ENDPOINT", "").rstrip("/")
AGENT_NAME = "RealEstateRecommendationAgent"
CHAT_MODEL_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "")

# --- Azure OpenAI (fallback chat + embeddings) ---
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "").rstrip("/")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "")
AZURE_OPENAI_DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME = os.getenv(
    "AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME", ""
)
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
COMMUTE_DESTINATION = os.getenv("COMMUTE_DESTINATION", "South Station, Boston, MA")

# When True, ranking excludes towns without full core data (useful for demos).
DEMO_MODE_FULL_DATA_ONLY = os.getenv("DEMO_MODE_FULL_DATA_ONLY", "false").lower() == "true"

# Phase 1.5: hybrid intent — LLM classify-only when Python confidence is low.
LLM_INTENT_FALLBACK_ENABLED = os.getenv("ENABLE_LLM_INTENT_FALLBACK", "true").lower() in (
    "1",
    "true",
    "yes",
)
LLM_INTENT_CONFIDENCE_THRESHOLD = float(os.getenv("LLM_INTENT_CONFIDENCE_THRESHOLD", "0.85"))

# Phase 4: LLM query planner (NL → QueryPlan JSON).
USE_LLM_QUERY_PLANNER = os.getenv("USE_LLM_QUERY_PLANNER", "true").lower() in (
    "1",
    "true",
    "yes",
)
LLM_QUERY_PLANNER_MAX_REPAIR_ATTEMPTS = int(
    os.getenv("LLM_QUERY_PLANNER_MAX_REPAIR_ATTEMPTS", "1")
)

# Phase 5: plan → execute → answer LLM (full query agent pipeline). Default production path.
USE_LLM_QUERY_AGENT = os.getenv("USE_LLM_QUERY_AGENT", "true").lower() in (
    "1",
    "true",
    "yes",
)
USE_LLM_ANSWER = os.getenv("USE_LLM_ANSWER", "true").lower() in ("1", "true", "yes")
USE_LLM_ANSWER_VALIDATOR = os.getenv("USE_LLM_ANSWER_VALIDATOR", "true").lower() in (
    "1",
    "true",
    "yes",
)

# Core fields required for data_quality_tier == "full"
CORE_FIELDS = (
    "latest_home_price",
    "safety_score",
    "school_score",
    "drive_minutes_to_boston",
    "dor_income_per_capita",
)

DEFAULT_RANKING_WEIGHTS = {
    "schools": 0.30,
    "safety": 0.25,
    "commute": 0.20,
    "affordability": 0.15,
    "economic": 0.10,
}
