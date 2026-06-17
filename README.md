# SuburbScout AI

**Live demo:** [suburbscout-ai.vercel.app](https://suburbscout-ai.vercel.app)

SuburbScout helps people compare Boston-area suburbs using real housing, school, safety, and commute data — not a generic chatbot. You ask in plain English (“safe towns under $900k within 35 minutes of Cambridge”), and the system plans what to look up, runs deterministic rankings on a curated dataset of **200 Massachusetts towns**, and returns a grounded answer with town cards and comparisons. An LLM handles language understanding and narration; it does not invent prices or commute times.

---

## What it does

You type a question about where to live. SuburbScout figures out whether you want a ranking, a side-by-side comparison, or a fact lookup, checks your constraints against real data, and explains the results in normal prose. It refuses when data is missing (e.g. commute to a city outside the dataset) instead of guessing. The React UI shows answers, top matches, comparison tables, and trust-gate refusals — never raw JSON.

---

## Tech stack

| Layer | Choice | Why |
|-------|--------|-----|
| **Frontend** | React 19, TypeScript, Vite, Tailwind | Fast static build; deploys to Vercel; talks to one API base URL |
| **API gateway** | FastAPI (Python 3.12) | Single `/api/query` contract for the UI; CORS, health, persistence |
| **Query pipeline** | Custom planner-first agent (`handle_query_v2`) | LLM emits structured `QueryPlan` JSON; Python executes on `suburbs.json` |
| **Cloud agent** | Microsoft Foundry Hosted Agent (`suburbscout-hosted`) | Same pipeline in a container; gateway normalizes responses for the UI |
| **LLM** | Azure OpenAI (e.g. `gpt-4o-mini`) | Planning + optional answer narration only |
| **Embeddings** | Azure OpenAI + local vector index | Semantic “vibe” search over town profiles |
| **Backend hosting** | Azure Container Apps (Consumption, scale-to-zero) | Low-cost public API; managed identity to Foundry |
| **Frontend hosting** | Vercel | Static `dist/` from `npm run build` |
| **CI** | GitHub Actions | Offline backend tests + frontend build on every push/PR to `main` |
| **Persistence (optional)** | Supabase Postgres | Saved searches and session preferences when `DATABASE_URL` is set |

**Note:** The frontend is **Vite + React**, not Next.js. All API calls go through `VITE_API_BASE_URL` (production: Azure Container Apps).

---

## Architecture

```text
┌─────────────────────────────────────────────────────────────────────────┐
│  Vercel — React UI (suburbscout-ai.vercel.app)                          │
│  POST /api/query  ·  GET /health  ·  GET /api/searches                 │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │ HTTPS (VITE_API_BASE_URL)
                                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Azure Container Apps — FastAPI gateway (app/api.py)                    │
│  BACKEND_AGENT_MODE=foundry  ·  FALLBACK_TO_LOCAL=true                  │
└───────────────┬─────────────────────────────┬───────────────────────────┘
                │ Foundry Responses API        │ fallback: local pipeline
                ▼                              ▼
┌───────────────────────────────┐   ┌─────────────────────────────────────┐
│  Foundry Hosted Agent         │   │  handle_query_v2 (same code path)   │
│  suburbscout-hosted @ ACR     │   │  planner → gates → executor → answer│
└───────────────┬───────────────┘   └──────────────────┬──────────────────┘
                │                                      │
                └──────────────────┬───────────────────┘
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Deterministic layer                                                    │
│  suburbs.json (200 towns) · ranking.py · commute_service · vector index │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  Optional: Supabase — search traces, session prefs                      │
└─────────────────────────────────────────────────────────────────────────┘
```

**Data pipeline (offline):** Raw CSVs/Excel under `agent_service/app/data/raw/` → `scripts/build_suburbs_dataset.py` → `app/data/suburbs.json` (+ percentile scores, commute fields).

---

## How the agent works

The system splits **reasoning** from **facts**:

1. **Plan (LLM)** — Azure OpenAI turns the user prompt into a `QueryPlan`: ops like `rank`, `compare`, `lookup`, `semantic_search`, or `unsupported`.
2. **Normalize + trust gates (Python)** — Fixes planner quirks, resolves town typos, blocks unsupported asks (live Zillow, commute to cities not in the dataset, too many towns in one compare).
3. **Execute (Python)** — `plan_executor` reads only `suburbs.json`, runs ranking/lookup/compare, optional Google Distance Matrix for dynamic commutes (cached).
4. **Answer (LLM, optional)** — Narrates from execution JSON; validator checks the prose against results.

If the LLM were removed after step 1, you would still get structured results. If you removed steps 2–3, you would get hallucinations. That split is intentional.

Production path: Vercel → ACA gateway → Foundry hosted agent (which runs the same `handle_query_v2` as local). The gateway parses hosted JSON into the shape the React app expects (`answer`, `top_matches`, `execution_status`, `trust_gate`, `source`, `metadata`).

---

## Data sources

All town facts come from a **curated 200-town** Greater Boston / MA commuter dataset (`app/data/suburb_list.csv` → `suburbs.json`).

| Signal | Source (raw files in `app/data/raw/`) |
|--------|----------------------------------------|
| Home prices | `housing_price_data.txt` |
| Schools | `MA_Public_Schools_2017.csv` |
| Crime / safety | SRS crime rates CSV |
| Economics | MA DOR income / EQV Excel |
| Commute to Boston | `processed/commute_times.csv` (Google Distance Matrix build) |
| Coastal flag | `coastal_towns.csv` |
| Regions | `suburb_list.csv` |

Scores (0–10) are **percentile ranks within the 200-town set**, not official government ratings. The UI states this on every answer.

**Not in the dataset:** Live MLS/Zillow, MBTA schedules, neighborhood-level demographics, towns outside the curated list (e.g. Providence commute comparisons are refused).

---

## Project structure

```text
suburbscout-ai/
├── frontend/                    # React + Vite UI → Vercel
│   ├── src/api/                 # client.ts, types (QueryResponse contract)
│   ├── src/components/          # search, results, trust/refusal panels
│   └── DEPLOY_VERCEL.md
├── agent_service/               # Python backend
│   ├── app/
│   │   ├── api.py               # FastAPI gateway
│   │   ├── query_agent.py       # handle_query_v2 pipeline
│   │   ├── llm_query_planner.py # NL → QueryPlan
│   │   ├── plan_executor.py     # deterministic execution
│   │   ├── plan_trust_gates.py  # plan-only refusals
│   │   ├── ranking.py           # score + filter towns
│   │   ├── foundry_client.py    # Foundry HTTP + JSON normalize
│   │   ├── hosted_query_agent.py# Foundry container adapter
│   │   └── data/                # suburbs.json, raw sources, vector index
│   ├── scripts/                 # dataset build, evals, deploy helpers
│   ├── tests/                   # unit + offline integration tests
│   ├── Dockerfile               # FastAPI gateway image (port 8000)
│   ├── Dockerfile.hosted        # Foundry hosted agent (port 8088)
│   └── docs/                    # DEPLOY_BACKEND_ACA.md, PHASE2_AZURE.md, …
├── .github/workflows/
│   ├── backend-tests.yml        # Python 3.12 offline tests
│   └── frontend-build.yml       # npm ci && npm run build
└── README.md
```

Deeper backend docs: [`agent_service/README.md`](agent_service/README.md).

---

## Local setup

### Prerequisites

- **Python 3.12+**
- **Node.js 20+**
- **Git**
- **Azure OpenAI** credentials (required for full agent path; CI runs without them)
- **Google Maps API key** (optional; dynamic commute to non-Boston destinations)
- **az login** (only for `BACKEND_AGENT_MODE=foundry` against cloud Foundry)

### 1. Clone and backend

```bash
git clone https://github.com/rmarathe-hub/suburbscout-ai.git
cd suburbscout-ai/agent_service

python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env       # fill Azure OpenAI, optional Foundry / Google / DATABASE_URL
```

Dataset is prebuilt in `app/data/suburbs.json`. To rebuild from raw sources:

```bash
python scripts/build_suburbs_dataset.py
```

### 2. Run API (local pipeline)

```bash
export BACKEND_AGENT_MODE=local
uvicorn app.api:app --reload --host 127.0.0.1 --port 8000
```

Smoke test:

```bash
curl -s http://127.0.0.1:8000/health | python -m json.tool
curl -s -X POST http://127.0.0.1:8000/api/query \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"What is the commute from Maynard to Boston?"}' | python -m json.tool
```

### 3. Run API (Foundry mode, optional)

```bash
az login
export BACKEND_AGENT_MODE=foundry
export FOUNDRY_AGENT_NAME=suburbscout-hosted
export FALLBACK_TO_LOCAL=true
# FOUNDRY_PROJECT_ENDPOINT in .env
uvicorn app.api:app --host 127.0.0.1 --port 8000
```

### 4. Run frontend

```bash
cd ../frontend
cp .env.example .env.local   # optional; dev uses Vite proxy to :8000
npm install
npm run dev
```

Open [http://127.0.0.1:5173](http://127.0.0.1:5173). Vite proxies `/health` and `/api` to the backend.

### 5. CLI chat (no UI)

```bash
cd agent_service && source venv/bin/activate
python -m app.chat
# or: python scripts/ask_query.py "Compare Acton and Burlington"
```

---

## Example queries

| Prompt | What happens |
|--------|----------------|
| `Find safe suburbs under 900k with good schools.` | Rank op → top_matches with scores and reasons |
| `Keep me below 30 minutes to Somerville and under 850k.` | Dynamic commute destination → filtered ranking |
| `Compare Acton and Burlington.` | Side-by-side comparison table |
| `What is the commute from Maynard to Cambridge?` | Lookup / commute pair from dataset or cache |
| `Acton vs Burlington if I work in Providence.` | Trust gate blocks — Providence not in dataset |
| `Give me live Zillow listings in Newton.` | Refusal — no live listing data |

---

## Testing

**Backend (offline, no cloud keys):**

```bash
cd agent_service
source venv/bin/activate
python scripts/verify_phase8_5_slice_a.py
python -m unittest tests.test_foundry_client tests.test_api_foundry_mode \
  tests.test_plan_preferences tests.test_commute_intent tests.test_commute_service \
  tests.test_trust_gate_layer tests.test_plan_trust_gates tests.test_plan_normalizer \
  tests.test_town_resolution -v
python -m pytest tests/test_e2e_expect.py -v
```

**Frontend:**

```bash
cd frontend
npm ci
npm run build
```

CI runs the same on push/PR to `main` (see `.github/workflows/`).

---

## Deployment

| Component | Where | Doc |
|-----------|--------|-----|
| React UI | Vercel | [`frontend/DEPLOY_VERCEL.md`](frontend/DEPLOY_VERCEL.md) |
| FastAPI gateway | Azure Container Apps | [`agent_service/docs/DEPLOY_BACKEND_ACA.md`](agent_service/docs/DEPLOY_BACKEND_ACA.md) |
| Query pipeline container | Foundry Hosted Agent + ACR | [`agent_service/docs/PHASE5_6_FOUNDRY_HOSTED.md`](agent_service/docs/PHASE5_6_FOUNDRY_HOSTED.md) |

Production API (example): `https://suburbscout-api.orangesand-275b63b0.eastus2.azurecontainerapps.io`

Set `VITE_API_BASE_URL` on Vercel to that URL. Add your Vercel origin to backend `FRONTEND_ALLOWED_ORIGINS` for CORS.

---

## What's next

1. **Map view** — Town results are cards and tables today; a geographic view of matches and commute radii is not built yet.
2. **Broader commute coverage** — Dynamic commutes depend on Google Distance Matrix + cache; expanding precomputed pairs would reduce cost and cold-start latency.
3. **User accounts** — Saved searches work with optional Postgres/Supabase; there is no end-user auth or multi-tenant session UI yet.

---

## Privacy and security

- API keys and `DATABASE_URL` live in environment variables only (`.env` is gitignored).
- No end-user PII is required to search.
- The agent uses public and licensed-style aggregate datasets, not live listing feeds.
- Do not commit `.env` or paste production secrets into scripts or docs.

---

## License

No `LICENSE` file in this repository yet. Treat as source-available for portfolio review unless you add a license.

---

**SuburbScout AI** — grounded suburb search for Greater Boston, built with Python, FastAPI, React, Azure OpenAI, and Microsoft Foundry.
