# Deploy FastAPI gateway to Azure Container Apps

SuburbScout production demo path:

```text
React frontend  →  Azure Container Apps (FastAPI gateway)  →  Foundry Hosted Agent  →  Azure OpenAI
```

This guide deploys the **gateway image** (`Dockerfile`, port 8000). It is separate from the **Foundry hosted agent** image (`Dockerfile.hosted`, port 8088) deployed via `phase5_push_acr.sh` + `phase6_deploy_foundry.py`.

## Why Azure Container Apps with scale-to-zero?

| Choice | Rationale |
|--------|-----------|
| **ACA Consumption** | Pay only when the API is handling requests; `minReplicas: 0` scales to zero when idle. |
| **Not “free-free”** | ACA is **pay-as-you-go**. Cold starts and Foundry/OpenAI usage still bill separately. |
| **Resume signal** | Shows containerized API gateway, managed identity, ACR, and cloud-native routing — stronger than localhost-only demos. |
| **vs App Service always-on** | App Service Basic tier runs 24/7; ACA scale-to-zero is cheaper for portfolio traffic. |

**Do not** create Azure Database for PostgreSQL for this demo. Keep **Supabase free tier** as external `DATABASE_URL` if you want search persistence.

## Readiness checklist

| Item | Status |
|------|--------|
| `Dockerfile` (uvicorn `app.api:app`, port 8000) | Ready |
| `app/data/suburbs.json` + vector index in image | Included via `COPY app/` |
| Foundry response normalization | `app/foundry_client.py` + `app/api.py` |
| `phase5_push_acr.sh` | **Hosted agent only** — do not reuse for gateway |
| `scripts/deploy_backend_aca.sh` | **Use this** for ACA gateway |
| Foundry hosted agent | Must already be active (`suburbscout-hosted`) |
| Auth in ACA | **Managed identity** on the container app (not `az login` in the container) |
| `azure-identity` | Pinned in `requirements.txt` for `DefaultAzureCredential` (Foundry gateway auth) |

### Optional follow-up (not required for first deploy)

- Set `FRONTEND_ALLOWED_ORIGINS` to your deployed React URL (Static Web Apps, Vercel, etc.).

## Required Azure resources

| Resource | Example name | Notes |
|----------|--------------|-------|
| Resource group | `rg-suburbscout` | Same region as Foundry (e.g. `eastus2`) |
| ACR | `suburbscout` | Login server: `suburbscout.azurecr.io` |
| Container Apps environment | `suburbscout-aca-env` | Consumption workload profile |
| Container App | `suburbscout-api` | FastAPI gateway |
| Foundry project + hosted agent | `suburbscout-hosted` | Already deployed |
| Azure OpenAI | existing deployment | For local fallback + hosted agent |

**Not required:** Azure Postgres, Redis, Application Gateway.

## Cost guardrails

1. **ACA Consumption** with `minReplicas: 0`, `maxReplicas: 1`.
2. **Low SKU:** `0.25` CPU, `0.5Gi` memory (defaults in deploy script).
3. **Reuse ACR** `suburbscout` — no second registry.
4. **Supabase external** — no Azure DB.
5. **Budget alerts** (manual in Azure Portal): **$5 / $10 / $20** monthly on the subscription or resource group.
6. **Scale down / delete** when not demoing (commands below).

Rough idle cost: ACA at zero replicas ≈ minimal platform charge; most demo cost is **Foundry + Azure OpenAI** per query, not the gateway container.

## Environment variables

Export in your shell before deploy. **Never commit** `.env` or paste secrets into the script.

### Required

| Variable | Example / notes |
|----------|-----------------|
| `FOUNDRY_PROJECT_ENDPOINT` | `https://<account>.services.ai.azure.com/api/projects/<project>` |
| `AZURE_OPENAI_ENDPOINT` | Required when `FALLBACK_TO_LOCAL=true` |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | e.g. `gpt-4o-mini` |

### Set by script (defaults)

| Variable | Default |
|----------|---------|
| `BACKEND_AGENT_MODE` | `foundry` |
| `FOUNDRY_AGENT_NAME` | `suburbscout-hosted` |
| `FALLBACK_TO_LOCAL` | `true` |

### Secrets (passed via ACA secret refs — from shell env)

| Variable | When needed |
|----------|-------------|
| `AZURE_OPENAI_API_KEY` | Local fallback if Foundry fails |
| `DATABASE_URL` | Optional — Supabase persistence |
| `GOOGLE_MAPS_API_KEY` | Optional — live dynamic commute (Boston-area cache still works without it for many queries) |

### Optional

| Variable | Purpose |
|----------|---------|
| `FOUNDRY_AGENT_VERSION` | Metadata in responses only |
| `FRONTEND_ALLOWED_ORIGINS` | CORS for your React host |
| `COMMUTE_DESTINATION` | Default Boston commute anchor |

## One-time setup

```bash
# Azure CLI + Container Apps extension
az login
az extension add --name containerapp --upgrade

# Confirm ACR
az acr show --name suburbscout --query loginServer -o tsv
# → suburbscout.azurecr.io
```

### Foundry RBAC for the container app (after first deploy)

The gateway calls Foundry with `DefaultAzureCredential` (system-assigned managed identity).

1. Get the app principal ID (printed at end of deploy script), or:

```bash
az containerapp identity show \
  --name suburbscout-api \
  --resource-group rg-suburbscout \
  --query principalId -o tsv
```

2. In Azure Portal → your **Foundry project** → Access control (IAM) → Add role assignment.
   - Role: **Azure AI Developer** (or project-equivalent that allows hosted agent invocation).
   - Member: the container app’s managed identity.

Without this, `/api/query` in Foundry mode returns auth errors (fallback may still work if `AZURE_OPENAI_API_KEY` is set).

## Deploy commands (manual)

From `agent_service/`, load secrets from your local `.env` into the shell (do not commit):

```bash
cd ~/Desktop/suburbscout-ai/agent_service
source venv/bin/activate

# Load secrets into shell (example — adjust path)
set -a && source .env && set +a

export RESOURCE_GROUP=rg-suburbscout
export LOCATION=eastus2
export IMAGE_TAG=gateway-v1

# First time only — creates ACA environment + app
chmod +x scripts/deploy_backend_aca.sh
CREATE_ACA_ENV=1 bash scripts/deploy_backend_aca.sh

# Subsequent releases — rebuild image + update app
bash scripts/deploy_backend_aca.sh
```

### Infrastructure overrides (optional)

```bash
export ACA_ENV_NAME=suburbscout-aca-env
export ACA_APP_NAME=suburbscout-api
export ACR_NAME=suburbscout
export IMAGE_REPO=suburbscout-api
export CPU=0.25
export MEMORY=0.5Gi
export MIN_REPLICAS=0
export MAX_REPLICAS=1
export USE_ACR_BUILD=1   # recommended on Apple Silicon (linux/amd64 cloud build)
```

## Smoke tests

Replace `<backend-url>` with the FQDN printed by the deploy script (`https://....azurecontainerapps.io`).

```bash
curl -sS https://<backend-url>/health | python -m json.tool

curl -sS -H "Content-Type: application/json" -X POST https://<backend-url>/api/query \
  -d '{"prompt":"Keep me below 30 minutes to Somerville and under 850k."}' | python -m json.tool

curl -sS -H "Content-Type: application/json" -X POST https://<backend-url>/api/query \
  -d '{"prompt":"Acton vs Burlington if I work in Providence."}' | python -m json.tool
```

### Expected results

| Test | Expected |
|------|----------|
| `/health` | `"status": "ok"`, `suburbs_dataset_loaded: true`, `backend_agent_mode: "foundry"`, `foundry_agent_configured: true` |
| Somerville query | `answer` is normal text (not raw JSON), `top_matches` is an array, `metadata.commute_destination` includes Somerville, `source: "foundry_hosted_agent"` when Foundry succeeds |
| Providence query | `execution_status: "blocked"`, `trust_gate: "commute_destination_compare"`, refusal in `answer`, empty `top_matches` |
| Foundry outage | With `FALLBACK_TO_LOCAL=true`, `source: "local_query_pipeline"` and API still responds |

## Scale down or delete

### Scale to zero (keep resources, no running replicas)

```bash
az containerapp update \
  --name suburbscout-api \
  --resource-group rg-suburbscout \
  --min-replicas 0 \
  --max-replicas 0
```

Restore demo:

```bash
az containerapp update \
  --name suburbscout-api \
  --resource-group rg-suburbscout \
  --min-replicas 0 \
  --max-replicas 1
```

### Delete only the gateway app

```bash
az containerapp delete \
  --name suburbscout-api \
  --resource-group rg-suburbscout \
  --yes
```

### Delete ACA environment (if no other apps)

```bash
az containerapp env delete \
  --name suburbscout-aca-env \
  --resource-group rg-suburbscout \
  --yes
```

### Delete entire resource group (destructive)

```bash
az group delete --name rg-suburbscout --yes --no-wait
```

**Warning:** Do not delete the resource group that hosts your Foundry project or ACR unless you intend to tear down everything.

## Security warnings

- **Never** hardcode API keys, `DATABASE_URL`, or Foundry tokens in `deploy_backend_aca.sh`, docs, or git.
- Use ACA **secret references** (script reads from your shell env at deploy time).
- Rotate keys in Supabase / Azure OpenAI if they were ever exposed.
- Restrict `FRONTEND_ALLOWED_ORIGINS` in production; `*` is not set by default.

## Related files

| File | Purpose |
|------|---------|
| `Dockerfile` | Gateway image (this deploy) |
| `Dockerfile.hosted` | Foundry hosted agent (phase 5/6) |
| `scripts/deploy_backend_aca.sh` | ACA build + deploy automation |
| `scripts/phase5_push_acr.sh` | Hosted agent image push only |
| `scripts/phase6_deploy_foundry.py` | Register hosted agent version |
| `scripts/verify_part2_docker.py` | Local Docker smoke test before ACA |

## Local Docker preflight (optional)

```bash
docker build -t suburbscout-api .
docker run --rm -p 8000:8000 --env-file .env suburbscout-api
python scripts/verify_part2_docker.py
```
