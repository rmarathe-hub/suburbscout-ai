#!/usr/bin/env bash
# Deploy SuburbScout FastAPI gateway to Azure Container Apps (Consumption, scale-to-zero).
#
# Architecture:
#   React frontend → ACA FastAPI (this image) → Foundry Hosted Agent → Azure OpenAI
#
# Prereqs:
#   - az login
#   - Azure Container Apps extension: az extension add --name containerapp
#   - ACR `suburbscout` exists with AcrPush for your user
#   - Foundry hosted agent `suburbscout-hosted` already deployed (phase5/6)
#   - Export secrets in your shell (never commit .env):
#       export FOUNDRY_PROJECT_ENDPOINT="https://....services.ai.azure.com/api/projects/..."
#       export AZURE_OPENAI_ENDPOINT="https://....openai.azure.com/"
#       export AZURE_OPENAI_DEPLOYMENT_NAME="gpt-4o-mini"
#       export AZURE_OPENAI_API_KEY="..."          # required if FALLBACK_TO_LOCAL=true
#       export DATABASE_URL="..."                  # optional (Supabase)
#       export GOOGLE_MAPS_API_KEY="..."           # optional (dynamic commute)
#
# Usage (from agent_service/):
#   export RESOURCE_GROUP=rg-suburbscout
#   export IMAGE_TAG=gateway-v1
#   CREATE_ACA_ENV=1 bash scripts/deploy_backend_aca.sh    # first time (creates env + app)
#   bash scripts/deploy_backend_aca.sh                     # rebuild image + update app
#
# Do not run this script from CI without reviewing cost and secrets handling.

set -euo pipefail

cd "$(dirname "$0")/.."

# --- Configurable infrastructure (no secrets) ---
RESOURCE_GROUP="${RESOURCE_GROUP:-rg-suburbscout}"
LOCATION="${LOCATION:-eastus2}"
ACA_ENV_NAME="${ACA_ENV_NAME:-suburbscout-aca-env}"
ACA_APP_NAME="${ACA_APP_NAME:-suburbscout-api}"
ACR_NAME="${ACR_NAME:-suburbscout}"
IMAGE_REPO="${IMAGE_REPO:-suburbscout-api}"
IMAGE_TAG="${IMAGE_TAG:-gateway-v1}"
CPU="${CPU:-0.25}"
MEMORY="${MEMORY:-0.5Gi}"
MIN_REPLICAS="${MIN_REPLICAS:-0}"
MAX_REPLICAS="${MAX_REPLICAS:-1}"
TARGET_PORT="${TARGET_PORT:-8000}"
USE_ACR_BUILD="${USE_ACR_BUILD:-1}"

# --- Runtime config (non-secret; override via env) ---
BACKEND_AGENT_MODE="${BACKEND_AGENT_MODE:-foundry}"
FOUNDRY_AGENT_NAME="${FOUNDRY_AGENT_NAME:-suburbscout-hosted}"
FALLBACK_TO_LOCAL="${FALLBACK_TO_LOCAL:-true}"
AZURE_OPENAI_API_VERSION="${AZURE_OPENAI_API_VERSION:-2024-12-01-preview}"
COMMUTE_DESTINATION="${COMMUTE_DESTINATION:-South Station, Boston, MA}"
FRONTEND_ALLOWED_ORIGINS="${FRONTEND_ALLOWED_ORIGINS:-http://localhost:5173,http://127.0.0.1:5173}"

FULL_IMAGE="${ACR_NAME}.azurecr.io/${IMAGE_REPO}:${IMAGE_TAG}"

die() {
  echo "ERROR: $*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"
}

require_cmd az

if ! az account show >/dev/null 2>&1; then
  die "Not logged in — run: az login"
fi

if [[ -z "${FOUNDRY_PROJECT_ENDPOINT:-}" ]]; then
  die "Set FOUNDRY_PROJECT_ENDPOINT (Foundry project URL, no trailing slash)."
fi

if [[ "$BACKEND_AGENT_MODE" == "foundry" && "${FALLBACK_TO_LOCAL}" == "true" ]]; then
  if [[ -z "${AZURE_OPENAI_ENDPOINT:-}" || -z "${AZURE_OPENAI_DEPLOYMENT_NAME:-}" ]]; then
    die "FALLBACK_TO_LOCAL=true requires AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_DEPLOYMENT_NAME."
  fi
  if [[ -z "${AZURE_OPENAI_API_KEY:-}" ]]; then
    echo "WARN: AZURE_OPENAI_API_KEY unset — local fallback will fail if Foundry is down."
  fi
fi

echo "=== SuburbScout ACA gateway deploy ==="
echo "  Resource group : ${RESOURCE_GROUP}"
echo "  Location       : ${LOCATION}"
echo "  ACA environment: ${ACA_ENV_NAME}"
echo "  Container app  : ${ACA_APP_NAME}"
echo "  Image          : ${FULL_IMAGE}"
echo "  Replicas       : min=${MIN_REPLICAS} max=${MAX_REPLICAS}"
echo "  CPU / memory   : ${CPU} / ${MEMORY}"
echo "  Agent mode     : ${BACKEND_AGENT_MODE} (Foundry agent: ${FOUNDRY_AGENT_NAME})"
echo ""

# --- 1. Build and push gateway image (Dockerfile, port 8000) ---
echo "=== Step 1: Build and push gateway image ==="
if [[ "${USE_ACR_BUILD}" == "1" ]]; then
  az acr build \
    --registry "$ACR_NAME" \
    --image "${IMAGE_REPO}:${IMAGE_TAG}" \
    --platform linux/amd64 \
    --file Dockerfile \
    .
else
  require_cmd docker
  docker build --platform linux/amd64 -f Dockerfile -t "${IMAGE_REPO}:${IMAGE_TAG}" .
  az acr login --name "$ACR_NAME"
  docker tag "${IMAGE_REPO}:${IMAGE_TAG}" "$FULL_IMAGE"
  docker push "$FULL_IMAGE"
fi
echo "Pushed: ${FULL_IMAGE}"
echo ""

# --- 2. Container Apps environment (once) ---
if ! az containerapp env show --name "$ACA_ENV_NAME" --resource-group "$RESOURCE_GROUP" >/dev/null 2>&1; then
  if [[ "${CREATE_ACA_ENV:-0}" != "1" ]]; then
    die "ACA environment '${ACA_ENV_NAME}' not found. Re-run with CREATE_ACA_ENV=1 to create it."
  fi
  echo "=== Step 2: Create Container Apps environment (Consumption) ==="
  az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none 2>/dev/null || true
  az containerapp env create \
    --name "$ACA_ENV_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --location "$LOCATION" \
    --output none
else
  echo "=== Step 2: ACA environment exists (${ACA_ENV_NAME}) ==="
fi
echo ""

# --- 3. Assemble env vars and secrets (from shell only) ---
declare -a SECRET_ITEMS=()
declare -a ENV_ITEMS=(
  "BACKEND_AGENT_MODE=${BACKEND_AGENT_MODE}"
  "FOUNDRY_AGENT_NAME=${FOUNDRY_AGENT_NAME}"
  "FOUNDRY_PROJECT_ENDPOINT=${FOUNDRY_PROJECT_ENDPOINT}"
  "FALLBACK_TO_LOCAL=${FALLBACK_TO_LOCAL}"
  "AZURE_OPENAI_API_VERSION=${AZURE_OPENAI_API_VERSION}"
  "COMMUTE_DESTINATION=${COMMUTE_DESTINATION}"
  "FRONTEND_ALLOWED_ORIGINS=${FRONTEND_ALLOWED_ORIGINS}"
  "USE_LLM_QUERY_AGENT=true"
  "USE_LLM_QUERY_PLANNER=true"
  "USE_LLM_ANSWER=true"
)

if [[ -n "${AZURE_OPENAI_ENDPOINT:-}" ]]; then
  ENV_ITEMS+=("AZURE_OPENAI_ENDPOINT=${AZURE_OPENAI_ENDPOINT}")
fi
if [[ -n "${AZURE_OPENAI_DEPLOYMENT_NAME:-}" ]]; then
  ENV_ITEMS+=("AZURE_OPENAI_DEPLOYMENT_NAME=${AZURE_OPENAI_DEPLOYMENT_NAME}")
fi
if [[ -n "${FOUNDRY_AGENT_VERSION:-}" ]]; then
  ENV_ITEMS+=("FOUNDRY_AGENT_VERSION=${FOUNDRY_AGENT_VERSION}")
fi
if [[ -n "${FOUNDRY_AGENT_RESPONSES_ENDPOINT:-}" ]]; then
  ENV_ITEMS+=("FOUNDRY_AGENT_RESPONSES_ENDPOINT=${FOUNDRY_AGENT_RESPONSES_ENDPOINT}")
fi

if [[ -n "${AZURE_OPENAI_API_KEY:-}" ]]; then
  SECRET_ITEMS+=("azure-openai-api-key=${AZURE_OPENAI_API_KEY}")
  ENV_ITEMS+=("AZURE_OPENAI_API_KEY=secretref:azure-openai-api-key")
fi
if [[ -n "${DATABASE_URL:-}" ]]; then
  SECRET_ITEMS+=("database-url=${DATABASE_URL}")
  ENV_ITEMS+=("DATABASE_URL=secretref:database-url")
fi
if [[ -n "${GOOGLE_MAPS_API_KEY:-}" ]]; then
  SECRET_ITEMS+=("google-maps-api-key=${GOOGLE_MAPS_API_KEY}")
  ENV_ITEMS+=("GOOGLE_MAPS_API_KEY=secretref:google-maps-api-key")
fi

# --- 4. Create or update Container App ---
APP_EXISTS=0
if az containerapp show --name "$ACA_APP_NAME" --resource-group "$RESOURCE_GROUP" >/dev/null 2>&1; then
  APP_EXISTS=1
fi

if [[ "$APP_EXISTS" -eq 0 ]]; then
  echo "=== Step 3: Create Container App ==="
  CREATE_ARGS=(
    --name "$ACA_APP_NAME"
    --resource-group "$RESOURCE_GROUP"
    --environment "$ACA_ENV_NAME"
    --image "$FULL_IMAGE"
    --target-port "$TARGET_PORT"
    --ingress external
    --min-replicas "$MIN_REPLICAS"
    --max-replicas "$MAX_REPLICAS"
    --cpu "$CPU"
    --memory "$MEMORY"
    --registry-server "${ACR_NAME}.azurecr.io"
    --registry-identity system
    --system-assigned
  )
  # Space-separated key=value pairs — values may contain commas (CORS, commute destination).
  CREATE_ARGS+=(--env-vars "${ENV_ITEMS[@]}")
  if ((${#SECRET_ITEMS[@]} > 0)); then
    CREATE_ARGS+=(--secrets "${SECRET_ITEMS[@]}")
  fi
  az containerapp create "${CREATE_ARGS[@]}" --output none

  echo "=== Step 4: Grant AcrPull to container app identity ==="
  PRINCIPAL_ID="$(az containerapp identity show \
    --name "$ACA_APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --query principalId -o tsv)"
  ACR_ID="$(az acr show --name "$ACR_NAME" --query id -o tsv)"
  az role assignment create \
    --assignee "$PRINCIPAL_ID" \
    --role AcrPull \
    --scope "$ACR_ID" \
    --output none 2>/dev/null || echo "WARN: AcrPull assignment may already exist."
else
  echo "=== Step 3: Update Container App ==="
  if ((${#SECRET_ITEMS[@]} > 0)); then
    az containerapp secret set \
      --name "$ACA_APP_NAME" \
      --resource-group "$RESOURCE_GROUP" \
      --secrets "${SECRET_ITEMS[@]}" \
      --output none
  fi
  az containerapp update \
    --name "$ACA_APP_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --image "$FULL_IMAGE" \
    --min-replicas "$MIN_REPLICAS" \
    --max-replicas "$MAX_REPLICAS" \
    --cpu "$CPU" \
    --memory "$MEMORY" \
    --set-env-vars "${ENV_ITEMS[@]}" \
    --output none
fi
echo ""

# --- 5. Foundry access reminder ---
echo "=== Step 4: Foundry auth (manual, once per app identity) ==="
echo "The container app uses DefaultAzureCredential (managed identity) for Foundry calls."
echo "Grant the app's system-assigned identity access to your Foundry project, e.g.:"
echo "  - Azure AI Developer / Cognitive Services User on the project scope"
echo "  - Or project-specific RBAC per your Foundry setup"
PRINCIPAL_ID="$(az containerapp identity show \
  --name "$ACA_APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query principalId -o tsv 2>/dev/null || echo "<principal-id>")"
echo "  Principal ID: ${PRINCIPAL_ID}"
echo ""

FQDN="$(az containerapp show \
  --name "$ACA_APP_NAME" \
  --resource-group "$RESOURCE_GROUP" \
  --query properties.configuration.ingress.fqdn -o tsv)"
BACKEND_URL="https://${FQDN}"

echo "=== Deploy complete ==="
echo "Backend URL: ${BACKEND_URL}"
echo ""
echo "Smoke tests:"
echo "  curl -sS ${BACKEND_URL}/health | python -m json.tool"
echo "  curl -sS -H 'Content-Type: application/json' -X POST ${BACKEND_URL}/api/query \\"
echo "    -d '{\"prompt\":\"Keep me below 30 minutes to Somerville and under 850k.\"}' | python -m json.tool"
echo "  curl -sS -H 'Content-Type: application/json' -X POST ${BACKEND_URL}/api/query \\"
echo "    -d '{\"prompt\":\"Acton vs Burlington if I work in Providence.\"}' | python -m json.tool"
echo ""
echo "Cost guardrails: min replicas=${MIN_REPLICAS}, max=${MAX_REPLICAS}, ${CPU} CPU, ${MEMORY}."
echo "Set Azure budget alerts at \$5 / \$10 / \$20 in the portal."
