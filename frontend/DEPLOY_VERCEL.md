# Deploy SuburbScout frontend to Vercel

React + Vite static site that calls the **Azure Container Apps** FastAPI gateway.

```text
Vercel (React)  →  VITE_API_BASE_URL  →  ACA FastAPI  →  Foundry Hosted Agent
```

## Prerequisites

- Backend live and smoke-tested (e.g. ACA URL returns `/health` and `/api/query`).
- Backend **CORS** allows your Vercel origin — set on the ACA gateway:

  ```bash
  # Example: add your Vercel URL to FRONTEND_ALLOWED_ORIGINS on the container app
  export FRONTEND_ALLOWED_ORIGINS="https://your-app.vercel.app,http://localhost:5173"
  # Re-run deploy_backend_aca.sh or az containerapp update --set-env-vars ...
  ```

## Vercel project settings

| Setting | Value |
|---------|--------|
| **Root Directory** | `frontend` |
| **Framework Preset** | Vite (auto-detected) |
| **Install Command** | `npm ci` |
| **Build Command** | `npm run build` |
| **Output Directory** | `dist` |

## Environment variables (Vercel → Settings → Environment Variables)

Set for **Production** (and Preview if you want preview deploys to hit ACA):

| Name | Value |
|------|--------|
| `VITE_API_BASE_URL` | `https://suburbscout-api.orangesand-275b63b0.eastus2.azurecontainerapps.io` |

Optional:

| Name | Value |
|------|--------|
| `VITE_FOUNDRY_TIMEOUT_MS` | `120000` (2 min for slow Foundry queries) |

**Do not** commit `.env` with real URLs to git if you prefer env-only config — Vercel injects `VITE_*` at build time.

Copy from `.env.example`:

```bash
cp .env.example .env.local   # local only — gitignored
```

## Manual deploy (CLI)

```bash
cd frontend
npm ci
npm run build

# One-time: vercel link (from repo root or frontend/)
npx vercel --cwd frontend

# Production deploy
npx vercel --cwd frontend --prod
```

Set `VITE_API_BASE_URL` in the Vercel dashboard before the first production build, or the app will fail API calls with a clear configuration error.

## Post-deploy smoke test

Replace with your Vercel URL:

```bash
# Frontend loads
curl -sS -o /dev/null -w "%{http_code}\n" https://your-app.vercel.app/

# Backend still healthy (direct)
curl -sS https://suburbscout-api.orangesand-275b63b0.eastus2.azurecontainerapps.io/health | python -m json.tool
```

In the browser:

1. Open the Vercel URL.
2. Header should show API online (health check via `VITE_API_BASE_URL`).
3. Search: *Keep me below 30 minutes to Somerville and under 850k.* → answer text + town cards.
4. Search: *Acton vs Burlington if I work in Providence.* → trust-gate refusal, no raw JSON.

## Local build verify (before commit)

```bash
cd frontend
npm ci
VITE_API_BASE_URL=https://suburbscout-api.orangesand-275b63b0.eastus2.azurecontainerapps.io npm run build
```

## Security

- No API keys belong in the frontend — only the public backend URL.
- Never commit `.env` with secrets; use Vercel env vars.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| “Cannot reach SuburbScout API” | Check `VITE_API_BASE_URL`, ACA ingress, cold start |
| CORS error in browser | Add Vercel origin to backend `FRONTEND_ALLOWED_ORIGINS` |
| `VITE_API_BASE_URL is not set` | Set env in Vercel and **redeploy** (Vite bakes vars at build time) |
| Request timeout | Increase `VITE_FOUNDRY_TIMEOUT_MS` |
