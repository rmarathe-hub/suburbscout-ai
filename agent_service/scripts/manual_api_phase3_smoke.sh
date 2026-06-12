#!/usr/bin/env bash
# Phase 3A manual smoke — Postgres persistence + sessions
# Prereqs: docker compose up -d, python scripts/init_db.py, python scripts/run_api.py
set -euo pipefail
BASE="${BASE_URL:-http://127.0.0.1:8000}"
SESSION="${SESSION_ID:-demo-phase3-$(date +%s)}"

query() {
  local n="$1"
  shift
  echo ""
  echo "========== [$n] $* (session=$SESSION) =========="
  curl -s -X POST "$BASE/api/query" \
    -H 'Content-Type: application/json' \
    -d "$(jq -n --arg p "$*" --arg s "$SESSION" '{prompt: $p, session_id: $s}')" \
    | python3 -m json.tool
}

echo "GET $BASE/health"
curl -s "$BASE/health" | python3 -m json.tool

query 1 "Find me a safe suburb under 900k with good schools."
query 2 "Make commute more important than schools."

echo ""
echo "========== Recent searches =========="
curl -s "$BASE/api/searches?limit=5" | python3 -m json.tool

echo ""
echo "========== Session preferences =========="
curl -s "$BASE/api/sessions/$SESSION" | python3 -m json.tool

RID="$(curl -s "$BASE/api/searches?limit=1" | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["searches"][0]["request_id"] if d.get("searches") else "")')"
if [[ -n "$RID" ]]; then
  echo ""
  echo "========== Full trace: $RID =========="
  curl -s "$BASE/api/searches/$RID" | python3 -m json.tool
fi
