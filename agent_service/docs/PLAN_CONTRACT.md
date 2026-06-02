# Phase 2 Step 3 — QueryPlan & Preferences contract

SuburbScout does **not** use a separate “preference extraction JSON” or weight vector (`schools: 0.30`, `diversity`, etc.). User intent becomes a validated **`QueryPlan`** with optional **`Preferences`** on `rank` ops.

## Pipeline (single path)

```text
User text
  → LLM planner (Azure)     raw QueryPlan JSON
  → plan_normalizer.py      rewrites (membership, coastal rank, semantic chain, prefs)
  → plan_trust_gates.py     block unsafe / out-of-scope plans
  → plan_executor.py        suburbs.json + vector index
  → answer LLM (optional)   prose from execution_results only
```

**Rule hints:** `parse_constraints()` is merged into planner context and `normalize_rank_preferences()`.

**Planner retry:** `LLM_QUERY_PLANNER_MAX_REPAIR_ATTEMPTS` (default `1`) — one repair pass on invalid JSON.

**Rule fallback:** If the planner still fails, `app/plan_fallback.py` may emit a minimal `rank` (or `semantic_search` + `rank`) plan for **simple filtered recommend** queries only (budget, commute, coastal, school/safety). Not used for lookup, compare, or membership.

Schema: `app/data/query_plan_schema.json` · models: `app/query_plan.py` · prefs: `app/schemas.py` (`Preferences`).

## Supported `Preferences` fields

| Field | Role |
|-------|------|
| `budget_max` | Max home price; ranking excludes no-housing towns when required |
| `max_commute_minutes` / `min_commute_minutes` | Drive time to `COMMUTE_DESTINATION` |
| `requires_coastal` | Coastal town filter |
| `school_priority`, `safety_priority`, `commute_priority`, `affordability_priority`, `economic_priority` | `high` \| `medium` \| `low` |
| `deprioritize_schools`, `deprioritize_safety` | Soften or invert those dimensions |
| `allow_low_safety`, `prefer_high_crime` | High-crime / cheap tradeoffs |
| `exclude_towns`, `named_towns`, `candidate_towns` | Town sets |
| `region_preference`, `county_preference`, `region_key` | Geography |
| `similar_to_town`, `safer_than_town`, `cheaper_than_town`, `quieter_than_town` | Relative constraints (executor/normalizer) |

## Not supported (do not document as ranking inputs)

- `diversity`, walkability, nightlife, politics, weather, job market  
- MBTA / transit routing  
- Neighborhood-within-town  
- Live MLS / Zillow  

Use `unsupported` op or trust gates for those asks.

## Canonical examples (phrase → ops)

| User phrase | Expected ops | Notes |
|-------------|--------------|-------|
| What is the commute from Maynard? | `lookup` | Town + field (commute) |
| Compare Acton and Framingham on schools and safety | `compare` | 2+ towns, columns from suburbs.json |
| Safe suburb under $900k with good schools | `rank` | Parsed budget + safety/school priorities |
| Quiet North Shore town with a coastal feel | `semantic_search`, `rank` | Vibe → candidates, then rank |
| Which neighborhood in Brookline is best for kids? | `unsupported` | Neighborhood category |

After normalization, coastal **lists** may be `rank` with `requires_coastal` only (no semantic). Pull-up typos may become `lookup` summary.

## Verify Step 3

```bash
cd agent_service && source venv/bin/activate
python scripts/verify_phase2_step3.py
python -m unittest tests.test_plan_fallback -v
```

See also: [`PHASE2_AZURE.md`](PHASE2_AZURE.md), [`app/plan_contract.py`](../app/plan_contract.py).
