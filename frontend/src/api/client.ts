import type {
  HealthResponse,
  PostQueryOptions,
  QueryRequest,
  QueryResponse,
  SearchListResponse,
  SearchTrace,
} from '@/api/types'

const DEFAULT_LOCAL_TIMEOUT_MS = 60_000
const DEFAULT_FOUNDRY_TIMEOUT_MS = 120_000

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
  const base = import.meta.env.VITE_API_BASE_URL?.trim() || 'http://127.0.0.1:8000'
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

export function getApiBaseUrl(): string {
  if (import.meta.env.DEV) {
    const target = import.meta.env.VITE_API_BASE_URL?.trim() || 'http://127.0.0.1:8000'
    return `${target} (via Vite dev proxy)`
  }
  return apiBaseUrl()
}

export async function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>('/health', { method: 'GET', timeoutMs: 10_000 })
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

  return request<QueryResponse>('/api/query', {
    method: 'POST',
    body: JSON.stringify(body),
    timeoutMs,
  })
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
