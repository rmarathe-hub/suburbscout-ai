# SuburbScout AI — Phase 1 Agent Service

Boston/MA suburb recommendation agent using real structured data, deterministic ranking,
Google commute times, and (Day 3) local vector search.

## Setup

```bash
cd agent_service
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in keys
```

Required for **Day 2 agent** (see `.env.example`):

| Variable | Purpose |
|----------|---------|
| `FOUNDRY_PROJECT_ENDPOINT` | Primary chat client (Microsoft Foundry project URL) |
| `AZURE_OPENAI_API_KEY` | Auth for Foundry + fallback |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | Chat model deployment (e.g. `gpt-4o-mini`) |
| `AZURE_OPENAI_ENDPOINT` | Fallback chat (resource base URL only — **no** `/openai/v1`) |

Optional for Day 1 pipeline: `GOOGLE_MAPS_API_KEY`, `COMMUTE_DESTINATION`, embedding deployment (Day 3).

The Agent Framework does **not** load `.env` automatically; `app/config.py` calls `load_dotenv()` on import.

### Production path (Phase 2 default)

**Query agent** is the default: natural language → LLM **QueryPlan** → normalizer → trust gates → deterministic execution on `suburbs.json` → grounded answer (or refusal).

| Entry point | Behavior |
|-------------|----------|
| `python -m app.chat` | **Query agent** (default when `USE_LLM_QUERY_AGENT=true`) |
| `python scripts/ask_query.py "…"` | One-shot query agent |
| `python -m app.chat --orchestrator` | Legacy regex orchestrator (fallback / comparison only) |
| `python -m app.chat --llm` | Legacy tool-calling Agent Framework path |

Set `USE_LLM_QUERY_AGENT=false` in `.env` only when debugging the old orchestrator.

```bash
cp .env.example .env   # USE_LLM_QUERY_AGENT=true by default
python -m app.chat
```

### Phase 2 Step 2 — Azure NL + behavior contract

Azure OpenAI (or Foundry chat) handles **language only**. All town facts and rankings come from **`plan_executor`** on `suburbs.json`.

| LLM may | LLM must not |
|---------|----------------|
| Emit `QueryPlan` JSON | Invent prices, scores, commute times, or towns |
| Narrate from `execution_results` | Rank without executor `top_matches` |
| Refuse when trust gates block | Claim live MLS / neighborhood / transit data |

Full contract: [`docs/PHASE2_AZURE.md`](docs/PHASE2_AZURE.md) · code: `app/llm_contract.py`

```bash
python scripts/verify_phase2_step2.py
# offline artifact checks only:
SKIP_LIVE_AZURE_CHECKS=1 python scripts/verify_phase2_step2.py
```

**Step 2 done when:** verify script passes with live Azure; `ask_query.py` and `python -m app.chat` behave the same on a lookup prompt.

### Phase 2 Step 3 — QueryPlan contract (no second preference JSON)

User intent is expressed only as **`QueryPlan`** + **`Preferences`** on `rank` ops — not a separate weight vector or `diversity` field.

| Component | Role |
|-----------|------|
| `llm_query_planner.py` | Azure → raw `QueryPlan` (retry once on bad JSON) |
| `plan_normalizer.py` | Merges `parse_constraints()` into rank prefs |
| `plan_fallback.py` | Narrow rule `rank` plan if planner still fails |
| `plan_executor.py` | Deterministic facts from `suburbs.json` |

Full contract + 5 canonical examples: [`docs/PLAN_CONTRACT.md`](docs/PLAN_CONTRACT.md)

```bash
python scripts/verify_phase2_step3.py
python -m unittest tests.test_plan_fallback -v
```

### Phase 2 Step 4 — Hardening

High-ROI normalizer and eval fixes (no new preference schema):

| Fix | Module |
|-----|--------|
| Neighborhood / live MLS → `unsupported` **before** pull-up/membership | `plan_normalizer._rewrite_hard_unsupported` |
| Commute/price/school lookups never → membership | `_is_protected_field_lookup` |
| Reading vs North Reading on pull-up/open | `query_patterns.extract_pull_up_town_name` |
| `plan_expect.expected_town` / `forbidden_towns` | `evals/planner_eval_scoring.py` |
| Audit JSONL: `request_id`, `latency_ms`, `raw_llm_plan` | `query_agent_audit.py` |

```bash
python scripts/verify_phase2_step4.py
# optional full regression (live Azure, several minutes):
python scripts/run_query_agent_verification.py --phase2-only
```

### Phase 2 Step 5 — PR regression gate

Fast check before push (~30–90s offline; add `--live` for 3 Azure smokes):

```bash
python scripts/verify_phase2_pr_gate.py
python scripts/verify_phase2_pr_gate.py --live   # +3 prompts, needs .env
SKIP_LIVE_AZURE_CHECKS=1 python scripts/verify_phase2_pr_gate.py   # offline only
```

| Step | What |
|------|------|
| Unit tests | normalizer, fallback, trust, golden executor, query_plan |
| Hardening | Reading pull-up, audit fields, plan_expect towns |
| Trust gate | 19 plan-level cases (offline) |
| Executor golden | 14 manifest cases (offline) |
| Live smoke (optional) | `app/evals/pr_gate_live_smoke.json` |

Results: `app/evals/results/pr_gate_*.json`

**Nightly / pre-release:** `python scripts/run_query_agent_verification.py --phase2-only`

### Phase 2 Step 6 — HTTP API (FastAPI)

Thin gateway over `handle_query_v2` — same brain as `python -m app.chat`.

```bash
pip install -r requirements.txt
python scripts/run_api.py              # http://127.0.0.1:8000
python scripts/verify_phase2_step6.py    # offline TestClient tests
python scripts/verify_phase2_step6.py --live   # one live query
```

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Liveness + `query_agent_configured` + `database` |
| `/api/query` | POST | Run query agent |
| `/api/searches` | GET | Recent searches (Phase 3A, needs `DATABASE_URL`) |
| `/api/searches/{request_id}` | GET | Full search trace (Phase 3A) |
| `/api/sessions/{session_id}` | GET | Session preferences (Phase 3A) |
| `/docs` | GET | OpenAPI UI |

**Request body:**

```json
{
  "prompt": "What is the commute from Maynard?",
  "save_audit": false,
  "debug": false
}
```

**Response (default):** `answer`, `execution_status`, `request_id`, `latency_ms`, optional `trust_gate`, `top_matches`. Set `"debug": true` to include `plan` and full `response`.

```bash
curl -s http://127.0.0.1:8000/health
curl -s -X POST http://127.0.0.1:8000/api/query \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"What is the commute from Maynard?"}'
```

### Phase 3A — PostgreSQL persistence

Adds durable search history, audit traces, and basic session memory **without changing** the Phase 2 query-agent brain. `suburbs.json` remains the ranking source of truth.

```bash
# Local Postgres
docker compose up -d
cp .env.example .env   # set DATABASE_URL + Azure keys
python scripts/init_db.py
python scripts/run_api.py
python scripts/verify_phase3a.py
python scripts/verify_phase3a.py --live-api   # Azure query + DB trace check
python scripts/verify_phase3a.py --full       # + phase2-only eval suite (slow)
bash scripts/manual_api_phase3_smoke.sh
```

| Env var | Default | Purpose |
|---------|---------|---------|
| `DATABASE_URL` | unset | Postgres connection string; unset = JSONL-only audit |
| `save_audit` (API) | `false` | JSONL fallback when Postgres unavailable |

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | + `database`: `ok` \| `unavailable` \| `not_configured` |
| `/api/query` | POST | + optional `session_id` for follow-ups |
| `/api/searches` | GET | Recent persisted searches (`?limit=20`) |
| `/api/searches/{request_id}` | GET | Full trace (plan, results, answer, audit) |
| `/api/sessions/{session_id}` | GET | Stored session preferences |

**Request body (with session):**

```json
{
  "prompt": "Make commute more important than schools.",
  "session_id": "demo-session-1",
  "save_audit": false,
  "debug": false
}
```

**Behavior:**

- When `DATABASE_URL` is set, every `/api/query` persists to Postgres (fail-soft — API still responds if DB is down).
- Legacy orchestrator `save_search_tool` writes to Postgres first, then `saved_searches.jsonl`.
- Session follow-ups load `latest_preferences` into planner context and merge updates after each turn.

**Files:** `app/db.py`, `app/db_models.py`, `app/repositories.py`, `alembic/`, `docker-compose.yml`

### Part 2 — Containerize API (Docker image for deploy)

Packages the FastAPI query agent for Azure Container Apps (Part 3). Image includes `suburbs.json` and the local vector index.

```bash
cd agent_service
docker build -t suburbscout-api .
docker run --rm -p 8000:8000 --env-file .env suburbscout-api
# other terminal:
python scripts/verify_part2_docker.py
curl -s -X POST http://127.0.0.1:8000/api/query \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"What is the commute from Maynard?"}'
```

| File | Purpose |
|------|---------|
| `Dockerfile` | Python 3.12 + uvicorn on port 8000 |
| `.dockerignore` | Excludes `.env`, venv, tests, eval results |

Run `alembic upgrade head` from your laptop (Part 1 / Supabase), not on container start. Use Supabase **transaction pooler** URL in `.env` for container/API runtime.

### Phase 0 — Query-plan agent prerequisites

Before building the two-stage agent (LLM query plan → execute on data → LLM answer), verify local data and Azure config:

```bash
source venv/bin/activate
python scripts/verify_phase0_prerequisites.py
```

**What Phase 0 confirms (no Postgres / vector DB server):**

| Artifact | Path | Role |
|----------|------|------|
| Town facts | `app/data/suburbs.json` | 200 towns — structured “database” for lookup, rank, compare |
| Town profiles | `app/data/town_profiles.json` | Text for embeddings |
| Vector index | `app/data/vector_index/embeddings.npy` + `metadata.json` | Local semantic search |

**Rebuild if missing:**

```bash
python scripts/build_suburbs_dataset.py   # → suburbs.json
python scripts/build_town_profiles.py     # → town_profiles.json
python scripts/build_vector_index.py      # → vector_index/ (needs embedding deployment in .env)
```

Skip live Azure API calls (offline artifact checks only): `SKIP_LIVE_AZURE_CHECKS=1 python scripts/verify_phase0_prerequisites.py`

### Phase 1 — Query plan schema

Structured plans (no LLM yet) live in `app/query_plan.py`. Supported ops:

| `op` | Purpose |
|------|---------|
| `lookup` | Up to 20 `{town, field}` items (fields: `summary`, `commute`, `price`, `school`, `safety`, `coastal`, `region`, `missing`, `tier`) |
| `compare` | 2–20 towns, optional `columns` (suburbs.json keys) |
| `rank` | `preferences` + `limit` (deterministic ranking in Phase 2 executor) |
| `semantic_search` | `query_text` + `top_k` (local vector index) |
| `unsupported` | Out-of-scope with `category` + `reason` |

```bash
# Export JSON Schema for planner prompts
python scripts/export_plan_schema.py   # → app/data/query_plan_schema.json

# Validate a plan file
python scripts/validate_plan_json.py tests/fixtures/plans/lookup_maynard_commute.json --pretty

# Unit tests
python -m unittest tests.test_query_plan -v
```

### Phase 2 — Plan executor

`app/plan_executor.py` runs validated plans against `suburbs.json` and the local vector index (no answer LLM).

```bash
# Execute a plan; print full ExecutionResult JSON
python scripts/run_plan.py tests/fixtures/plans/lookup_maynard_commute.json

# Answer-stage context only
python scripts/run_plan.py tests/fixtures/plans/compare_newton_brookline.json --context-only

# Template refusal when status is not ok/partial
python scripts/run_plan.py tests/fixtures/plans/lookup_maynard_commute.json --refusal

python -m unittest tests.test_plan_executor -v
```

| `ExecutionResult.status` | Meaning |
|--------------------------|---------|
| `ok` | All ops returned usable data |
| `partial` | Some data missing (e.g. field null, compare partial) |
| `not_found` | Town(s) not in 200-town dataset |
| `no_rows` | Rank/semantic returned no matches |
| `out_of_scope` | `unsupported` op |

### Phase 3 — Golden plan regression

Hand-written `QueryPlan` JSON files (from phase2 / tier15 prompts) plus `tests/fixtures/golden_plans/manifest.json`.

```bash
# Run executor regression (skips live semantic by default)
SKIP_SEMANTIC_GOLDEN=1 python scripts/run_golden_plans.py

# Include semantic_search golden (needs Azure embeddings)
python scripts/run_golden_plans.py

python -m unittest tests.test_golden_plans tests.test_plan_executor tests.test_query_plan -v
```

| Golden id | Covers |
|-----------|--------|
| `ml_01`, `ml_06` | Multi-town lookup |
| `mc_03` … `mc_20` | Compare tables (3–20 towns) |
| `ctrl_gate_21` | Plan validation rejects 21 towns |
| `tier15_*` | Rank exclude, not found, unsupported |

### Phase 4 — LLM query planner

`app/llm_query_planner.py` converts natural language → validated `QueryPlan` JSON (Azure chat via Agent Framework).

```bash
# Plan only
python scripts/plan_query.py "What is commute from Maynard, housing cost in Newton?"

# Plan + execute against suburbs.json
python scripts/plan_query.py "Compare Newton, Needham, and Wellesley on schools" --execute

# Optional smoke (live LLM, first 6 manifest prompts with text)
python scripts/run_planner_smoke.py
```

| Env var | Default | Purpose |
|---------|---------|---------|
| `USE_LLM_QUERY_PLANNER` | `true` | Enable planner |
| `LLM_QUERY_PLANNER_MAX_REPAIR_ATTEMPTS` | `1` | Retry after invalid JSON/plan |
| `SKIP_LIVE_LLM_PLANNER` | — | Skip live unit test |

```bash
python -m unittest tests.test_llm_query_planner -v
```

### Phase 5 — Grounded answer + query agent

`app/llm_answer.py` narrates from `execution_results` only.  
`app/query_agent.py` runs the full pipeline: **plan → execute → answer** (or template refusal).

| `execution_status` | User sees |
|--------------------|-----------|
| `ok`, `partial` | Answer LLM (validator checks prices) or template fallback |
| `not_found`, `no_rows`, `out_of_scope`, `invalid_plan` | Template refusal — **no answer LLM** |

```bash
# One-shot query agent (default path)
python scripts/ask_query.py "What is commute from Maynard?"

# Interactive chat (default)
python -m app.chat

# Plan + execute only (no answer LLM)
python scripts/plan_query.py "Compare Newton and Brookline" --execute
```

| Env var | Default | Purpose |
|---------|---------|---------|
| `USE_LLM_QUERY_AGENT` | `true` | Route `run_agent` / chat to query-agent pipeline |
| `USE_LLM_ANSWER` | `true` | LLM narration when execution succeeds |
| `USE_LLM_ANSWER_VALIDATOR` | `true` | Reject answers with prices not in execution JSON |

```bash
python -m unittest tests.test_llm_answer -v
```

Legacy orchestrator is **fallback only** (`--orchestrator` or `USE_LLM_QUERY_AGENT=false`).

### Phase 6 — Plan trust gates

`app/plan_trust_gates.py` runs **before** execution in the query-agent path:

- Plan limits (max 20 lookups / compares)
- Reuses orchestrator trust rules via `plan_to_query_route` → `evaluate_trust_gate`
- Blocks silent-wrong cases: unsupported compare fields, wrong commute destination, too many towns, etc.
- Non-blocking warnings (e.g. partial unsupported rank) surface as `tradeoff_warning`

Executor hybrid: if `semantic_search` runs before `rank`, candidate towns auto-limit ranking even when `use_semantic_candidates` was omitted.

```bash
python scripts/check_plan_trust.py "Compare Newton vs Needham on walkability"
python scripts/check_plan_trust.py --plan tests/fixtures/golden_plans/phase2/mc_03.json "Compare 3 towns on schools"

python -m unittest tests.test_plan_trust_gates -v
```

### Phase 7 — Production wiring + eval

The query agent is the **default production path** (`USE_LLM_QUERY_AGENT=true` in `.env`).

| Entry point | Behavior |
|-------------|----------|
| `python -m app.chat` | Query agent (default) |
| `python -m app.chat --query-agent` | Force query agent (same as default) |
| `python -m app.chat --orchestrator` | Legacy regex orchestrator |
| `run_agent(...)` | Query agent when `USE_LLM_QUERY_AGENT=true` |

```bash
# One-shot
python scripts/ask_query.py "What is commute from Maynard?"

# Interactive (with save / audit)
python -m app.chat --save

# Live eval suite (8 prompts, writes app/evals/results/query_agent_eval_*.json)
python scripts/run_query_agent_eval.py

# Offline eval scoring tests
python -m unittest tests.test_query_agent_phase7 -v
```

Audit log (optional): `app/query_agent_audit.jsonl` when `save_searches=True` / `--save` in query-agent mode.

| Env var | Default | Purpose |
|---------|---------|---------|
| `USE_LLM_QUERY_AGENT` | `true` | Query agent as default; set `false` for legacy orchestrator |
| `SKIP_LIVE_QUERY_AGENT_EVAL` | — | Skip live eval script |

### Layered eval (QueryPlan pipeline)

Four layers test the query agent in isolation and end-to-end. **Offline layers** run without Azure; **live layers** need `USE_LLM_QUERY_PLANNER=true` and credentials.

```bash
# All offline layers + unit tests
python scripts/run_layered_eval.py

# Include live planner (100 prompts) + E2E (150 prompts)
python scripts/run_layered_eval.py --live
```

| Layer | Script / tests | What it checks | Target |
|-------|----------------|----------------|--------|
| **1 Planner** | `scripts/run_planner_eval.py` | NL → `QueryPlan` vs 100 fixtures | op/town/field accuracy ≥90% |
| **2 Executor** | `tests/test_golden_plans.py`, `tests/test_executor_golden_extended.py` | Hand-written plans → `suburbs.json` / vectors, no LLM | 100% pass |
| **3 Trust gates** | `scripts/run_trust_gate_eval.py` | Block before execute; no answer LLM on refusal | ≥95% pass |
| **4 E2E** | `scripts/run_e2e_query_agent_eval.py` | Full pipeline on 150 fresh prompts | ≥135/150 pass; 0 hallucinated facts; 0 wrong-dest rank |

**Generate fixtures:**

```bash
python scripts/generate_planner_eval_100.py   # 100 prompts + tests/fixtures/planner_eval/*.json
python scripts/generate_e2e_150.py            # app/evals/e2e_query_agent_150.json
```

**Artifacts:** `app/evals/results/planner_eval_100_*.json`, `trust_gate_eval_*.json`, `e2e_query_agent_150_*.json`

| File | Purpose |
|------|---------|
| `app/evals/planner_eval_100.json` | Layer 1 manifest |
| `app/evals/trust_gate_plan_eval.json` | Layer 3 hand-written plans + expected gates |
| `app/evals/e2e_query_agent_150.json` | Layer 4 randomized prompts |
| `app/evals/planner_eval_scoring.py` | Op / town / field scoring |
| `app/evals/layered_eval_checks.py` | Hallucination + commute-destination checks |

---

## Day 1 — Data pipeline

Run from `agent_service/`:

```bash
# 1. Fetch commute times (uses Google API + cache)
python scripts/build_commute_data.py

# 2. Merge all sources → suburbs.json
python scripts/build_suburbs_dataset.py

# 3. Validate
python scripts/validate_dataset.py

# 4. Smoke test ranking (no LLM)
python scripts/smoke_test_ranking.py
```

---

## Day 2 — Microsoft Agent Framework agent

A real **Agent Framework** agent (`RealEstateRecommendationAgent`) calls registered tools backed by `suburbs.json` and `ranking.py`. This is not a hand-written if/else chatbot.

### Chat client: Foundry-first, OpenAI fallback

1. **Primary:** `FoundryChatClient` via `FOUNDRY_PROJECT_ENDPOINT` + `AZURE_OPENAI_DEPLOYMENT_NAME`
2. **Fallback:** `OpenAIChatClient` with `AZURE_OPENAI_ENDPOINT` + API key if Foundry construction fails

For local API-key auth, Foundry’s OpenAI subclient is patched to use `project_client.get_openai_client(api_key=...)`. The fallback client uses Responses API version `preview` (not the chat-completions date in `AZURE_OPENAI_API_VERSION`).

### Core tools (5 — Day 2 baseline)

| Tool | Role |
|------|------|
| `parse_preferences_tool` | Rule-based prefs from natural language |
| `rank_suburbs_tool` | Deterministic ranking from `suburbs.json` |
| `compare_suburbs_tool` | Side-by-side two towns |
| `explain_results_tool` | Template explanation from tool data only |
| `save_search_tool` | Append audit line to `app/saved_searches.jsonl` |

Recommendation workflow: **parse → rank → explain → save**. Compare workflow: **compare → save**.

### Run the agent (Day 2 — 3 test prompts)

```bash
source venv/bin/activate
python -m app.test_agent   # now runs 7 prompts; Day 2 subset is first 3
```

Or run the automated Day 2 checker (3 prompts only):

```bash
python scripts/verify_day2_step4.py
```

### Day 2 verification scripts (step-by-step)

```bash
python scripts/verify_day2_step1.py   # deps + env
python scripts/verify_day2_step2.py   # tools only (no LLM)
python scripts/verify_day2_step3.py   # agent + optional live ping
python scripts/verify_day2_step4.py   # full 3-prompt agent test
```

Skip live model call on step 3:

```bash
SKIP_LIVE_AGENT_RUN=1 python scripts/verify_day2_step3.py
```

### Score disclaimer

All **0–10 scores** are **percentile ranks within the 200-town dataset**, not official government ratings. The agent and tools repeat this in outputs.

### Data rules (agent)

- Only towns in `suburbs.json` (200-town list)
- No invented prices, crime, commute, or school data
- Missing housing → `latest_home_price = null`, `data_quality_tier = partial`
- Budget queries exclude towns without housing prices

---

## Day 3 — Vector search + semantic tool

Local embedding search over **template town profiles** (deterministic text from `suburbs.json`, not LLM blurbs). Semantic search **narrows candidates only**; final order always comes from `rank_suburbs_tool`.

### Build town profiles and vector index

Run once after Day 1 data exists (re-run when `suburbs.json` changes):

```bash
source venv/bin/activate
python scripts/build_town_profiles.py    # → app/data/town_profiles.json
python scripts/build_vector_index.py     # → app/data/vector_index/
```

`build_vector_index.py` skips re-embedding when `town_profiles.json` is unchanged (use `--force` to rebuild).

### Agent tools (6 total)

Day 2 core tools plus:

| Tool | Role |
|------|------|
| `semantic_town_search_tool` | Embed query → top-k town **candidates** from local index |

| Query type | Workflow |
|------------|----------|
| Structured (budget, schools, safety, commute) | parse → rank → explain → save |
| Fuzzy / vibe (“coastal feel”, “like Lexington but cheaper”) | semantic → parse → rank (`candidate_towns`) → explain → save |
| Compare | compare → save |

Required env for embeddings: `AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME` (see `.env.example`).

### Run the full Phase 1 test suite (7 prompts)

```bash
python -m app.test_agent
```

### Interactive CLI (try your own prompts)

```bash
python -m app.chat              # query agent (default); --orchestrator for legacy path
python -m app.chat --json       # full JSON each turn
python -m app.chat --save       # append turns (query_agent_audit.jsonl when using query agent)
python -m app.chat --verbose    # show tool call logs
```

Type `quit`, `exit`, or `q` to leave.

Prompts: 3 structured/compare (Day 2) + 4 fuzzy/semantic (Day 3).

Automated Phase 1 completion check:

```bash
python scripts/verify_day3_step5.py
```

Skip live agent calls when needed:

```bash
SKIP_LIVE_AGENT_RUN=1 python scripts/verify_day3_step5.py
```

### Day 3 verification scripts (step-by-step)

```bash
python scripts/verify_day3_step1.py   # embeddings env + smoke test
python scripts/verify_day3_step2.py   # town profiles
python scripts/verify_day3_step3.py   # vector index + search
python scripts/verify_day3_step4.py   # semantic tool + agent wiring
python scripts/verify_day3_step5.py   # 7-prompt Phase 1 completion
```

Skip live embedding or agent calls:

```bash
SKIP_LIVE_EMBEDDING_RUN=1 python scripts/verify_day3_step3.py
SKIP_LIVE_AGENT_RUN=1 python scripts/verify_day3_step4.py
```

### Phase 1 end-to-end (after data refresh)

```bash
python scripts/build_commute_data.py      # if commute cache stale
python scripts/build_suburbs_dataset.py
python scripts/validate_dataset.py
python scripts/build_town_profiles.py
python scripts/build_vector_index.py
python scripts/verify_day3_step5.py
```

---

## Phase 1.1 — Legacy orchestrator (fallback)

Phase 1.1 adds a **deterministic regex orchestrator** (superseded by the query agent for production). Use `--orchestrator` to compare or debug. Python routing + tools run the pipeline; the model is optional fallback for unsupported queries.

### Architecture

```text
User prompt
  → query_router.py          (intent + fixed pipeline)
  → constraint_parser.py     (budget, coastal, commute, region, …)
  → orchestrator.py          (run tools in order)
  → ranking.py + suburbs.json (hard filters + scores)
  → response_validator.py    (block bad answers)
  → structured JSON response
```

**Rules (unchanged from Phase 1):**

- Source of truth: `suburbs.json` + `ranking.py`
- Semantic search narrows candidates only; final rank is always deterministic
- Scores are 0–10 percentiles within the 200-town dataset
- Missing housing → `null`, no invented data
- Lookup queries never substitute unknown towns

### New / updated modules

| Module | Role |
|--------|------|
| `geo_enrichment.py` | `is_coastal`, `region_key` on suburbs |
| `constraint_parser.py` | Strict preference parsing (budget, coastal, commute min/max, …) |
| `query_router.py` | Rule-based intent routing (lookup, compare, recommend, …) |
| `response_validator.py` | Property checks before returning answers |
| `orchestrator.py` | Deterministic tool pipelines |
| `get_town_facts_tool` | Single-town lookup (no ranking, no substitution) |

Agent tools: **7 total** (Day 2 core + semantic + lookup).

### Interactive CLI (legacy orchestrator)

```bash
python -m app.chat --orchestrator   # regex router + tools (no query-plan LLM)
python -m app.chat --json             # full JSON each turn
python -m app.chat --save             # saved_searches.jsonl
python -m app.chat --llm              # legacy LLM tool-calling agent
python -m app.chat --verbose          # show logs
```

Most prompts return in ~1–5s (no LLM round-trip). Semantic/vibe queries still call embeddings to narrow candidates, then rank deterministically.

### Quality eval suite (99 prompts)

Property-based checks (intent, budget, coastal, commute, lookup found/not found, etc.) — not exact wording.

```bash
python scripts/run_quality_evals.py
python scripts/run_quality_evals.py --category lookup
python scripts/run_quality_evals.py --category semantic
python scripts/run_quality_evals.py --limit 20
python scripts/run_quality_evals.py --json-out eval_results.json
```

Target pass rate: **≥ 85%** (current suite: 99/99 on orchestrator).

Eval prompts: `app/evals/phase1_1_quality_prompts.json`

### 150-prompt manual quality check (response review)

Curated prompts for human review — captures full orchestrator responses, no pass/fail scoring.

Prompt file: `app/evals/quality_check_150_prompts.json` (categories A–J)

```bash
# Regenerate JSON from source list (if prompts change)
python scripts/build_quality_check_150.py

# Run all 150 and save JSON + markdown (when you're ready)
python scripts/run_150_quality_check.py

# Partial runs
python scripts/run_150_quality_check.py --category A_lookup
python scripts/run_150_quality_check.py --category H_semantic_vibe --limit 5
```

Output goes to `app/evals/results/quality_check_150_<timestamp>.json` and `.md`.

### Phase 1.1 verification (step-by-step)

```bash
python scripts/verify_phase1_1_step1.py   # coastal / region_key data
python scripts/verify_phase1_1_step2.py   # get_town_facts_tool
python scripts/verify_phase1_1_step3.py   # constraint_parser
python scripts/verify_phase1_1_step4.py   # ranking hard filters
python scripts/verify_phase1_1_step5.py   # query_router
python scripts/verify_phase1_1_step6.py   # response_validator
python scripts/verify_phase1_1_step7.py   # orchestrator
python scripts/verify_phase1_1_step8.py   # quality eval suite
```

**Phase 1.1 completion (runs Steps 1–8):**

```bash
python scripts/verify_phase1_1_complete.py
```

Run a subset:

```bash
python scripts/verify_phase1_1_complete.py --from-step 5 --to-step 8
```

### Known limitations (Phase 1.1)

- Commute data is to **South Station, Boston** only (not arbitrary workplaces)
- No live Zillow/Redfin/MLS feeds — curated snapshot in `suburbs.json`
- Highway corridor tags (Route 9, I-90, I-495) not yet in structured data (Phase 1.2)
- Typo handling suggests close matches but does not auto-correct town names
- LLM agent remains as fallback for truly unsupported/off-topic queries

---

## Data sources

Raw files live in `app/data/raw/`:

- `housing_price_data.txt` — `house_price` only, newest year per town
- `DOR_Income_EQV_Per_Capita.xlsx` — DOR income/EQV per capita (not median household income)
- `SRS Crime Rates by Local Police Department (Ranked by Population).csv`
- `MA_Public_Schools_2017.csv`
- `suburb_list.csv` — 200-town product scope (from `boston_extended_commuter_towns.csv`)

Towns missing housing data keep `latest_home_price = null` and `data_quality_tier = partial`.
No placeholder prices are invented.

## Project layout

```
agent_service/
  app/
    config.py              # paths, env, weights
    data_loader.py         # raw file loaders
    town_normalizer.py     # name aliases
    geo_enrichment.py      # coastal + region_key (Phase 1.1)
    constraint_parser.py   # strict preference parsing (Phase 1.1)
    query_router.py        # intent routing (Phase 1.1)
    response_validator.py  # output validation (Phase 1.1)
    orchestrator.py        # deterministic pipelines (Phase 1.1)
    ranking.py             # deterministic ranking + hard filters
    schemas.py             # Pydantic models
    embeddings.py          # Azure OpenAI embedding client
    town_profiles.py       # template profile builder
    vector_store.py        # local cosine search
    tools.py               # Agent Framework @tool functions (7 tools)
    chat_client.py         # Foundry-first client factory
    real_estate_agent.py   # Agent + orchestrator entry
    chat.py                # interactive CLI
    test_agent.py          # Phase 1 seven-prompt runner
    evals/
      phase1_1_quality_prompts.json
      runner.py
    saved_searches.jsonl   # audit log (append-only)
    data/
      suburb_list.csv
      coastal_towns.csv    # curated coastal list (Phase 1.1)
      suburbs.json         # generated
      town_profiles.json   # generated
      vector_index/        # embeddings.npy + metadata.json
      processed/
  scripts/
    build_commute_data.py
    build_suburbs_dataset.py
    build_town_profiles.py
    build_vector_index.py
    validate_dataset.py
    smoke_test_ranking.py
    run_quality_evals.py
    verify_day2_step1.py … verify_day2_step4.py
    verify_day3_step1.py … verify_day3_step5.py
    verify_phase1_1_step1.py … verify_phase1_1_step8.py
    verify_phase1_1_complete.py
```
