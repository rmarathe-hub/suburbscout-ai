import type { QueryResponse, SearchTrace } from '@/api/types'

/** Reconstruct a QueryResponse from a persisted search trace for sidebar replay. */
export function traceToQueryResponse(trace: SearchTrace): QueryResponse {
  const results = trace.recommendation_result?.results ?? {}
  const trustGate = trace.query_plan?.trust_gate
  const messageCode = trace.message_code ?? results.message_code ?? null

  const source =
    messageCode === 'foundry_hosted_agent' ? 'foundry_hosted_agent' : 'local_query_pipeline'

  const topMatches = Array.isArray(results.top_matches) ? results.top_matches : []
  const comparison =
    results.comparison && typeof results.comparison === 'object' ? results.comparison : null

  return {
    answer: trace.answer?.text?.trim() || '',
    execution_status: trace.execution_status ?? results.execution_status ?? 'ok',
    request_id: trace.request_id,
    latency_ms: trace.latency_ms ?? null,
    message_code: messageCode,
    trust_gate: trustGate?.gate_type ?? null,
    trust_gate_blocks: trustGate?.blocks_pipeline ?? null,
    used_answer_llm: trace.answer?.used_answer_llm ?? false,
    top_matches: topMatches,
    comparison,
    source,
    metadata: {
      backend_agent_mode: source === 'foundry_hosted_agent' ? 'foundry' : 'local',
      restored_from_trace: true,
    },
    tradeoff_warning: null,
    score_disclaimer: null,
    error: null,
  }
}
