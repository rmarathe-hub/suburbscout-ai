/** Mirrors Phase 7 FastAPI schemas (agent_service/app/api_schemas.py). */

export type QuerySource = 'foundry_hosted_agent' | 'local_query_pipeline'

export type DatabaseStatus = 'ok' | 'unavailable' | 'not_configured'

export interface QueryRequest {
  prompt?: string
  query?: string
  session_id?: string | null
  save_audit?: boolean
  debug?: boolean
}

export interface QueryMetadata {
  agent_name?: string
  agent_version?: string | null
  backend_agent_mode?: string
  foundry_error_code?: string
  [key: string]: unknown
}

export interface QueryResponse {
  answer: string
  execution_status: string
  request_id: string
  latency_ms?: number | null
  message_code?: string | null
  trust_gate?: string | null
  trust_gate_blocks?: boolean | null
  used_answer_llm?: boolean
  top_matches: Record<string, unknown>[]
  plan?: Record<string, unknown> | null
  raw_llm_plan?: Record<string, unknown> | null
  response?: Record<string, unknown> | null
  source?: QuerySource | null
  metadata?: QueryMetadata | null
  comparison?: Record<string, unknown> | null
  tradeoff_warning?: string | null
  score_disclaimer?: string | null
  error?: string | null
}

export interface HealthResponse {
  status: string
  query_agent_configured: boolean
  suburbs_dataset_loaded: boolean
  database: DatabaseStatus
  backend_agent_mode?: string
  foundry_agent_configured?: boolean
  foundry_agent_endpoint?: string | null
}

export interface SearchSummary {
  request_id: string
  prompt: string
  execution_status?: string | null
  message_code?: string | null
  latency_ms?: number | null
  session_id?: string | null
  created_at?: string | null
}

export interface SearchListResponse {
  searches: SearchSummary[]
}

/** Full trace from GET /api/searches/{request_id} (Postgres persistence). */
export interface SearchTrace {
  request_id: string
  prompt: string
  execution_status?: string | null
  message_code?: string | null
  latency_ms?: number | null
  session_id?: string | null
  created_at?: string | null
  query_plan?: {
    raw_llm_plan?: Record<string, unknown> | null
    normalized_plan?: Record<string, unknown> | null
    trust_gate?: {
      gate_type?: string | null
      blocks_pipeline?: boolean | null
    } | null
  } | null
  recommendation_result?: {
    result_type?: string | null
    results?: {
      top_matches?: Record<string, unknown>[]
      comparison?: Record<string, unknown> | null
      lookup?: Record<string, unknown> | null
      semantic_candidates?: unknown
      execution_status?: string | null
      message_code?: string | null
    } | null
  } | null
  answer?: {
    text?: string | null
    used_answer_llm?: boolean
  } | null
}

export interface PostQueryOptions {
  sessionId?: string | null
  saveAudit?: boolean
  debug?: boolean
  /** Override default timeout (ms). Foundry hosted agent may need 120_000+. */
  timeoutMs?: number
}

/** Normalized town card for UI (from messy top_matches payloads). */
export interface TownMatch {
  name: string
  score: number | null
  reasons: string[]
  tradeoffs: string[]
  price: number | null
  schoolScore: number | null
  safetyScore: number | null
  commuteMinutes: number | null
  commuteDestinationLabel: string | null
  dataQualityTier: string | null
  raw: Record<string, unknown>
}

export interface ComparisonColumn {
  key: string
  label: string
}

export interface ComparisonRow {
  town: string
  values: Record<string, number | string | boolean | null>
}

/** Normalized comparison for side-by-side UI. */
export interface ComparisonData {
  rows: ComparisonRow[]
  columns: ComparisonColumn[]
  towns: string[]
  errors: string[]
}
