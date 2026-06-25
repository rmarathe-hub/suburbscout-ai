import type {
  HealthResponse,
  PostQueryOptions,
  QueryRequest,
  QueryResponse,
  SearchListResponse,
  SearchTrace,
  WarmHealthResponse,
} from '@/api/types'

const DEFAULT_LOCAL_TIMEOUT_MS = 60_000
const DEFAULT_FOUNDRY_TIMEOUT_MS = 180_000
const HEALTH_TIMEOUT_MS = 30_000
const HEALTH_MAX_ATTEMPTS = 4
const HEALTH_RETRY_BASE_DELAY_MS = 2_500
const WARM_TIMEOUT_MS = 120_000
const QUERY_MAX_ATTEMPTS = 3
const QUERY_RETRY_BASE_DELAY_MS = 2_000

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly detail: unknown

  constructor(status: number, message: string, code: string, detail: unknown = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.detail = detail
  }
}

function apiBaseUrl(): string {
  // Dev: same-origin requests via Vite proxy (see vite.config.ts) — avoids CORS on any port.
  if (import.meta.env.DEV) {
    return ''
  }
  const base = import.meta.env.VITE_API_BASE_URL?.trim()
  if (!base) {
    throw new ApiError(
      0,
      'VITE_API_BASE_URL is not set — configure it in Vercel project settings.',
      'missing_api_base_url',
    )
  }
  return base.replace(/\/$/, '')
}

async function parseJsonBody<T>(response: Response): Promise<T> {
  const text = await response.text()
  if (!text) {
    throw new ApiError(response.status, 'Empty response from API', 'empty_body')
  }
  try {
    return JSON.parse(text) as T
  } catch {
    throw new ApiError(response.status, 'Invalid JSON from API', 'invalid_json', text.slice(0, 200))
  }
}

function extractErrorMessage(status: number, body: unknown): string {
  if (body && typeof body === 'object') {
    const record = body as Record<string, unknown>
    if (typeof record.detail === 'string') return record.detail
    if (Array.isArray(record.detail)) {
      return record.detail
        .map((item) => {
          if (item && typeof item === 'object' && 'msg' in item) {
            return String((item as { msg: unknown }).msg)
          }
          return String(item)
        })
        .join('; ')
    }
    if (typeof record.message === 'string') return record.message
  }
  return `Request failed with status ${status}`
}

async function request<T>(
  path: string,
  init: RequestInit & { timeoutMs?: number } = {},
): Promise<T> {
  const { timeoutMs = DEFAULT_LOCAL_TIMEOUT_MS, ...fetchInit } = init
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), timeoutMs)

  try {
    const response = await fetch(`${apiBaseUrl()}${path}`, {
      ...fetchInit,
      signal: controller.signal,
      headers: {
        Accept: 'application/json',
        ...(fetchInit.body ? { 'Content-Type': 'application/json' } : {}),
        ...fetchInit.headers,
      },
    })

    const body = await parseJsonBody<unknown>(response)

    if (!response.ok) {
      throw new ApiError(
        response.status,
        extractErrorMessage(response.status, body),
        response.status === 422 ? 'validation_error' : 'http_error',
        body,
      )
    }

    return body as T
  } catch (error) {
    if (error instanceof ApiError) throw error
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiError(408, 'Request timed out', 'timeout')
    }
    if (error instanceof TypeError) {
      throw new ApiError(0, 'Cannot reach SuburbScout API — is the backend running?', 'network')
    }
    throw error
  } finally {
    window.clearTimeout(timer)
  }
}

function isRetryableApiError(error: unknown): boolean {
  if (!(error instanceof ApiError)) return false
  if (error.code === 'network' || error.code === 'timeout') return true
  if (error.status === 0 || error.status === 408) return true
  return error.status === 502 || error.status === 503 || error.status === 504
}

async function delay(ms: number): Promise<void> {
  await new Promise((resolve) => window.setTimeout(resolve, ms))
}

async function requestWithRetry<T>(
  path: string,
  init: RequestInit & { timeoutMs?: number },
  options: { maxAttempts: number; baseDelayMs: number },
): Promise<T> {
  let lastError: unknown
  for (let attempt = 1; attempt <= options.maxAttempts; attempt += 1) {
    try {
      return await request<T>(path, init)
    } catch (error) {
      lastError = error
      const canRetry = attempt < options.maxAttempts && isRetryableApiError(error)
      if (!canRetry) throw error
      await delay(options.baseDelayMs * attempt)
    }
  }
  throw lastError
}

export function getApiBaseUrl(): string {
  if (import.meta.env.DEV) {
    const target = import.meta.env.VITE_API_BASE_URL?.trim() || 'http://127.0.0.1:8000'
    return `${target} (via Vite dev proxy)`
  }
  return apiBaseUrl()
}

export async function getHealth(): Promise<HealthResponse> {
  return requestWithRetry<HealthResponse>(
    '/health',
    { method: 'GET', timeoutMs: HEALTH_TIMEOUT_MS },
    { maxAttempts: HEALTH_MAX_ATTEMPTS, baseDelayMs: HEALTH_RETRY_BASE_DELAY_MS },
  )
}

let foundryWarmPromise: Promise<void> | null = null

/** Background Foundry hosted-agent warm-up (ACA health alone does not wake the agent). */
export function startFoundryWarmup(): void {
  if (foundryWarmPromise) return
  foundryWarmPromise = request<WarmHealthResponse>('/health/warm', {
    method: 'POST',
    timeoutMs: WARM_TIMEOUT_MS,
  })
    .then(() => undefined)
    .catch(() => undefined)
}

/** Wait for in-flight Foundry warm-up before the user's first query. */
export async function ensureFoundryWarm(): Promise<void> {
  startFoundryWarmup()
  if (foundryWarmPromise) {
    await foundryWarmPromise
  }
}

/** Clear warm-up state so a reconnect runs a fresh hosted-agent wake-up. */
export function resetFoundryWarmup(): void {
  foundryWarmPromise = null
}

/** @deprecated Use getHealth + startFoundryWarmup */
export function warmupBackend(): void {
  void getHealth().catch(() => {
    /* Retries and UI state are handled by useHealth */
  })
}

export async function postQuery(
  prompt: string,
  options: PostQueryOptions = {},
): Promise<QueryResponse> {
  const trimmed = prompt.trim()
  if (!trimmed) {
    throw new ApiError(400, 'prompt is required', 'validation_error')
  }

  const body: QueryRequest = {
    prompt: trimmed,
    session_id: options.sessionId ?? null,
    save_audit: options.saveAudit ?? false,
    debug: options.debug ?? false,
  }

  const timeoutMs =
    options.timeoutMs ??
    (import.meta.env.VITE_FOUNDRY_TIMEOUT_MS
      ? Number(import.meta.env.VITE_FOUNDRY_TIMEOUT_MS)
      : DEFAULT_FOUNDRY_TIMEOUT_MS)

  return requestWithRetry<QueryResponse>(
    '/api/query',
    {
      method: 'POST',
      body: JSON.stringify(body),
      timeoutMs,
    },
    { maxAttempts: QUERY_MAX_ATTEMPTS, baseDelayMs: QUERY_RETRY_BASE_DELAY_MS },
  )
}

export async function listSearches(limit = 10): Promise<SearchListResponse> {
  return request<SearchListResponse>(`/api/searches?limit=${limit}`, {
    method: 'GET',
    timeoutMs: 15_000,
  })
}

export async function getSearch(requestId: string): Promise<SearchTrace> {
  const id = requestId.trim()
  if (!id) {
    throw new ApiError(400, 'request_id is required', 'validation_error')
  }
  return request<SearchTrace>(`/api/searches/${encodeURIComponent(id)}`, {
    method: 'GET',
    timeoutMs: 15_000,
  })
}
