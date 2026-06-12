import type { QueryResponse } from '@/api/types'

const LIVE_LISTING_PATTERN = /\b(zillow|redfin|mls|live listing|live listings)\b/i
const REFUSAL_PROSE_PATTERN =
  /\b(cannot|can't|unable|do not|don't|not provide|not access|out of scope|unsupported)\b/i

export type RefusalKind = 'out_of_scope' | 'unsupported' | 'foundry_error' | 'trust_gate' | 'live_data'

export interface RefusalInfo {
  kind: RefusalKind
  title: string
  message: string
}

export function detectRefusal(response: QueryResponse | null): RefusalInfo | null {
  if (!response) return null

  if (response.error === 'foundry_agent_error') {
    return {
      kind: 'foundry_error',
      title: 'Hosted agent unavailable',
      message:
        'The Foundry hosted agent could not complete this request. Try again in a moment, or switch the backend to local mode for deterministic answers.',
    }
  }

  if (response.execution_status === 'out_of_scope' || response.message_code === 'unsupported_request') {
    return {
      kind: 'unsupported',
      title: 'Outside SuburbScout scope',
      message:
        response.answer ||
        'This request is outside what SuburbScout can answer with our curated town dataset.',
    }
  }

  if (response.trust_gate && response.trust_gate_blocks) {
    return {
      kind: 'trust_gate',
      title: 'Request blocked by trust gate',
      message:
        response.answer ||
        'SuburbScout blocked this query to avoid inventing data we cannot verify.',
    }
  }

  if (looksLikeLiveListingRefusal(response.answer)) {
    return {
      kind: 'live_data',
      title: 'No live listing data',
      message:
        'SuburbScout uses a curated 200-town dataset — not live Zillow, Redfin, or MLS feeds. Try asking about median prices, schools, safety, or commute from our data.',
    }
  }

  return null
}

export function looksLikeLiveListingRefusal(answer: string | null | undefined): boolean {
  if (!answer?.trim()) return false
  return LIVE_LISTING_PATTERN.test(answer) && REFUSAL_PROSE_PATTERN.test(answer)
}
