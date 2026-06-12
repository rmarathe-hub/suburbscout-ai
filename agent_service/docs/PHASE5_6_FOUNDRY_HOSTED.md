# Phase 5–6 — ACR + Foundry Hosted Agent (short demo)

Deploy SuburbScout as a **Foundry Hosted Agent** (container from ACR). This is separate from your local FastAPI image (`Dockerfile` on port 8000).

| Image | Port | Purpose |
|-------|------|---------|
| `Dockerfile` | 8000 | FastAPI `/api/query` (local + Supabase) |
| `Dockerfile.hosted` | 8088 | Foundry **Responses** protocol (`/responses`) |

Hosted agents require **linux/amd64**. On Apple Silicon use `USE_ACR_BUILD=1` or `docker build --platform linux/amd64`.

## Prerequisites

- Azure subscription + `az login`
- **Foundry Project Manager** on your Foundry project ([roles](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent))
- Existing Foundry project + chat model deployment (same one you use locally)
- `FOUNDRY_PROJECT_ENDPOINT` in `.env` (you likely already have this)
- Supabase `DATABASE_URL` (optional but recommended for `save_search_tool`)

Install deploy SDK (one time):

```bash
cd agent_service
source venv/bin/activate
pip install "azure-ai-projects>=2.1.0"
pip install -r requirements-hosted.txt   # local hosted_main testing only
```

## Phase 5 — Create ACR + push image

### 5a. Create ACR (once)

```bash
az group create -n rg-suburbscout-foundry -l eastus2
az acr create -g rg-suburbscout-foundry -n suburbscoutacr --sku Basic
```

Pick a **globally unique** ACR name if `suburbscoutacr` is taken.

### 5b. Build and push

**Option A — Cloud build (recommended on Mac):**

```bash
export ACR_NAME=suburbscoutacr
export IMAGE_TAG=v1
USE_ACR_BUILD=1 bash scripts/phase5_push_acr.sh
```

**Option B — Local Docker:**

```bash
export ACR_NAME=suburbscoutacr
export IMAGE_TAG=v1
bash scripts/phase5_push_acr.sh
```

Result image: `suburbscoutacr.azurecr.io/suburbscout-hosted:v1`

### 5c. Grant Foundry project identity AcrPull

1. Azure Portal → your **Foundry project** → **Identity** → copy **Object (principal) ID**
2. ACR → **Access control (IAM)** → **Add role assignment**
3. Role: **AcrPull** (or Container Registry Repository Reader)
4. Assign to the project managed identity

(`azd deploy` does this automatically; manual deploy needs this step.)

## Phase 6 — Deploy Hosted Agent

Set env vars (from your `.env`):

```bash
export FOUNDRY_PROJECT_ENDPOINT="https://<account>.services.ai.azure.com/api/projects/<project>"
export AZURE_AI_MODEL_DEPLOYMENT_NAME="<your-chat-deployment-name>"
export DATABASE_URL="<supabase-postgres-url>"   # optional
```

Deploy:

```bash
python scripts/phase6_deploy_foundry.py \
  --image suburbscoutacr.azurecr.io/suburbscout-hosted:v1 \
  --agent-name suburbscout-hosted \
  --invoke "What is the commute from Maynard?"
```

Wait until status is **active**, then capture screenshots.

## Smoke tests (proof)

### Local (before cloud push)

```bash
az login
python -m app.hosted_main
# separate terminal:
curl -sS -H "Content-Type: application/json" -X POST http://localhost:8088/responses \
  -d '{"input": "What is the commute from Maynard?", "stream": false}'
```

### Foundry portal

1. [Foundry portal](https://ai.azure.com) → your project → **Build** → **Agents**
2. Open **suburbscout-hosted** → **Playground**
3. Prompt: `What is the commute from Maynard?`

### Supabase (optional)

Confirm a new row in `searches` after a hosted turn that calls `save_search_tool`.

## Cost control — tear down after demo

Hosted agents bill for **container compute per hour** + **model tokens**.

```bash
# Delete agent version (portal or SDK) when done
# Delete resource group if you created rg-suburbscout-foundry only for this demo:
az group delete -n rg-suburbscout-foundry --yes --no-wait
```

Keep Supabase + your existing Azure OpenAI resource — those are separate.

## Alternative: full `azd` scaffold

Fastest Microsoft-supported path (creates ACR + RBAC for you):

```bash
azd ext install microsoft.foundry
azd ai agent init -m "https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/agent-framework/responses/01-basic/agent.manifest.yaml"
azd provision
azd deploy
```

Then swap in SuburbScout’s `Dockerfile.hosted` / `hosted_main.py` for the sample. Use that if manual ACR/RBAC steps are painful.

## Resume one-liner

> Dockerized SuburbScout agent (Agent Framework + suburbs tools) deployed as a **Foundry Hosted Agent** from **Azure Container Registry**, with Postgres persistence on Supabase.

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `AcrPullUnauthorized` | AcrPull on project managed identity |
| Image wrong arch | Rebuild with `--platform linux/amd64` |
| Agent `failed` | Portal → agent version → error details; check model deployment name env var |
| Local 8088 auth errors | Run `az login`; set `FOUNDRY_PROJECT_ENDPOINT` + deployment name in `.env` |
