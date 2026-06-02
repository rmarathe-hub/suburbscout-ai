#!/usr/bin/env bash
# Manual API smoke — 8 prompts (server: python scripts/run_api.py)
set -euo pipefail
BASE="${BASE_URL:-http://127.0.0.1:8000}"

query() {
  local n="$1"
  shift
  echo ""
  echo "========== [$n] $* =========="
  curl -s -X POST "$BASE/api/query" \
    -H 'Content-Type: application/json' \
    -d "$(jq -n --arg p "$*" '{prompt: $p}')" \
    | python3 -m json.tool
}

echo "GET $BASE/health"
curl -s "$BASE/health" | python3 -m json.tool

query 1 "What is the commute from Maynard?"
query 2 "Open Reading."
query 3 "Compare Acton and Framingham on schools and safety"
query 4 "Safe suburb under $900k with good schools"
query 5 "Quiet North Shore town with a coastal feel"
query 6 "Which neighborhood in Brookline is best for kids?"
query 7 "Would Boxford be accepted as a town name?"
query 8 "Show me current Zillow listings in Newton right now"
