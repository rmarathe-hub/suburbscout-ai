# SuburbScout Frontend (Phase 8)

React dashboard for the SuburbScout AI suburb recommendation agent. Talks only to the Phase 7 FastAPI gateway — not directly to Foundry or the query pipeline.

## Prerequisites

- Node.js 20+
- Backend running at `http://127.0.0.1:8000` (see `agent_service/README.md`)

## Setup

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

Open [http://127.0.0.1:5173](http://127.0.0.1:5173) or [http://localhost:5173](http://localhost:5173).

**Connection troubleshooting:** In dev, Vite proxies `/health` and `/api` to the backend (no CORS issues on any port). If the header shows “API offline”, confirm `curl http://127.0.0.1:8000/health` works and restart both servers. If Vite says “Port 5173 is in use”, it may start on **5174** — that’s fine with the dev proxy.

## Environment

| Variable | Default | Purpose |
|----------|---------|---------|
| `VITE_API_BASE_URL` | `http://127.0.0.1:8000` | FastAPI gateway |
| `VITE_FOUNDRY_TIMEOUT_MS` | `120000` | Optional POST timeout for Foundry mode |

## API contract

The UI uses three endpoints:

- `GET /health` — backend mode, dataset, database status
- `POST /api/query` — `{ "prompt": "..." }` (or `query` alias), `save_audit: true` for history
- `GET /api/searches?limit=10` — saved search sidebar (requires `DATABASE_URL` on API)
- `GET /api/searches/{request_id}` — reload a saved result without re-querying

Response fields used: `answer`, `execution_status`, `source`, `metadata`, `top_matches`, `comparison`, `tradeoff_warning`, `score_disclaimer`, `message_code`, `error`.

## Demo prompts (manual checklist)

Run with backend in **local** mode first, then optionally **foundry**.

| Prompt | Expected UI |
|--------|-------------|
| `What is the commute from Maynard to Boston?` | Answer + badges; empty town grid |
| `Find safe suburbs under 900k with good schools.` | Answer + up to 10 town cards |
| `Compare Acton and Burlington.` | Answer + comparison table with prices/scores |
| `Open Reading.` | Lookup-style answer |
| `Give me live Zillow listings in Newton.` | Refusal panel (local: `out_of_scope`; Foundry: prose + panel) |

## Scripts

```bash
npm run dev      # Vite dev server (:5173)
npm run build    # Production build
npm run preview  # Preview production build
```

## Architecture

```
src/
  api/           client + TypeScript types
  components/
    layout/      AppShell, Header, BackendStatus
    search/      HeroSearch, PromptChips
    results/     AnswerCard, TownGrid, ComparisonPanel
    trust/       TrustPanel, RefusalPanel
    sidebar/     SavedSearches
  hooks/         useSearch, useHealth, useSavedSearches
  lib/           format, townMatch, comparison, refusal parsers
```

## Notes

- No raw JSON is shown in the UI.
- `debug` is always `false` from the frontend.
- Foundry queries may take 10–60s; the loading steps are cosmetic timers.
- Saved searches require Postgres (`DATABASE_URL`) on the API.
- Sidebar click loads the persisted trace via `GET /api/searches/{id}` (in-memory cache for the current session avoids a second fetch). Falls back to a live `POST /api/query` only if the trace is missing (404) or DB is unavailable (503).
