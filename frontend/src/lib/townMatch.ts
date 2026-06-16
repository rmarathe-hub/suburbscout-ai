import type { TownMatch } from '@/api/types'

function asNumber(value: unknown): number | null {
  if (typeof value === 'number' && !Number.isNaN(value)) return value
  if (typeof value === 'string' && value.trim() !== '') {
    const n = Number(value)
    return Number.isNaN(n) ? null : n
  }
  return null
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.filter((item): item is string => typeof item === 'string')
}

function pickData(raw: Record<string, unknown>): Record<string, unknown> {
  const nested = raw.data
  if (nested && typeof nested === 'object' && !Array.isArray(nested)) {
    return nested as Record<string, unknown>
  }
  return raw
}

/** Normalize one top_matches entry from local or Foundry payloads. */
export function parseTownMatch(raw: Record<string, unknown>): TownMatch {
  const data = pickData(raw)
  const name =
    (typeof raw.name === 'string' && raw.name) ||
    (typeof data.name === 'string' && data.name) ||
    (typeof raw.town === 'string' && raw.town) ||
    'Unknown town'

  return {
    name,
    score: asNumber(raw.score),
    reasons: asStringArray(raw.reasons ?? raw.key_reasons ?? raw.matched_factors),
    tradeoffs: asStringArray(raw.tradeoffs),
    price: asNumber(data.latest_home_price ?? raw.latest_home_price),
    schoolScore: asNumber(data.school_score ?? raw.school_score),
    safetyScore: asNumber(data.safety_score ?? raw.safety_score),
  commuteMinutes: asNumber(
      data.drive_minutes_to_destination ??
        raw.drive_minutes_to_destination ??
        data.drive_minutes_to_boston ??
        raw.drive_minutes_to_boston,
    ),
    commuteDestinationLabel:
      typeof data.commute_destination_label === 'string'
        ? data.commute_destination_label
        : typeof raw.commute_destination_label === 'string'
          ? raw.commute_destination_label
          : null,
    dataQualityTier:
      typeof data.data_quality_tier === 'string'
        ? data.data_quality_tier
        : typeof raw.data_quality_tier === 'string'
          ? raw.data_quality_tier
          : null,
    raw,
  }
}

export function parseTownMatches(matches: Record<string, unknown>[] | null | undefined): TownMatch[] {
  if (!matches?.length) return []
  return matches.map(parseTownMatch)
}
