# Phase 2 Step 2 — Azure NL + behavior contract

SuburbScout’s **production path** is the query agent: Azure plans and explains; Python executes on real data.

## Pipeline

```text
User question
  → Azure OpenAI (planner LLM)     QueryPlan JSON
  → plan_normalizer.py             fixes / rewrites
  → plan_trust_gates.py            block unsafe plans
  → plan_executor.py               suburbs.json + vector index
  → Azure OpenAI (answer LLM)      optional narration from execution JSON only
```

**Facts and rankings always come from** `suburbs.json`, `ranking.py`, and the local vector index — never from model weights alone.

## LLM may

- Emit a **QueryPlan** (`lookup`, `compare`, `rank`, `membership`, `semantic_search`, `unsupported`).
- Use **semantic_search** embeddings to narrow candidates, then **rank** deterministically.
- Write a **grounded answer** from `execution_results` when status is `ok` or `partial`.
- **Refuse** clearly when trust gates block (neighborhood, live MLS, wrong commute destination, etc.).

## LLM must not

- Invent towns, prices, commute minutes, scores, or crime rates.
- Return a ranked list without executor `top_matches` from a `rank` op.
- Claim live Zillow/MLS, neighborhood detail, MBTA/transit, or demographics.
- Replace a failed lookup with a different town.
- Skip trust gates or answer from general knowledge when execution was blocked.

## Environment variables

Copy `agent_service/.env.example` → `.env` and set:

| Variable | Purpose |
|----------|---------|
| `AZURE_OPENAI_API_KEY` | Auth |
| `AZURE_OPENAI_ENDPOINT` | Resource URL (base only) |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | Chat model (planner + answer) |
| `AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME` | Embeddings for semantic search |
| `FOUNDRY_PROJECT_ENDPOINT` | Optional; Foundry chat tried before OpenAI fallback |
| `USE_LLM_QUERY_PLANNER` | `true` |
| `USE_LLM_QUERY_AGENT` | `true` (default) |

Optional: `GOOGLE_MAPS_API_KEY` only when **rebuilding** commute cache — not required for chat.

## Verify Step 2

```bash
cd agent_service
source venv/bin/activate
python scripts/verify_phase2_step2.py
```

Offline only (no Azure API calls):

```bash
SKIP_LIVE_AZURE_CHECKS=1 python scripts/verify_phase2_step2.py
```

**Done when:** script ends with `Phase 2 Step 2 verification: PASSED` and one live lookup returns `execution_status=ok` with an answer grounded in execution data.

## Manual smoke

```bash
python scripts/ask_query.py "What is the commute from Maynard?"
python -m app.chat
```

Legacy regex path (comparison only): `python -m app.chat --orchestrator`

## Scope limits (product)

- 200 curated MA towns in `suburbs.json`
- Commute: drive time to `COMMUTE_DESTINATION` (default South Station, Boston)
- No MLS/live market, no neighborhood-level safety/schools, no transit routing

See also: [`PLAN_CONTRACT.md`](PLAN_CONTRACT.md) (QueryPlan + Preferences), `app/llm_contract.py`, `app/data/query_plan_schema.json`.
