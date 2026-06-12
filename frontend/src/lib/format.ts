const EM_DASH = '—'

/** Format median home price for display ($814.5k, $1.2M). */
export function formatPrice(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return EM_DASH
  if (value >= 1_000_000) {
    const millions = value / 1_000_000
    return `$${millions >= 10 ? Math.round(millions) : millions.toFixed(1)}M`
  }
  if (value >= 1_000) {
    return `$${(value / 1_000).toFixed(1)}k`
  }
  return `$${Math.round(value)}`
}

/** Format 0–10 percentile score. */
export function formatScore(value: number | null | undefined, digits = 1): string {
  if (value == null || Number.isNaN(value)) return EM_DASH
  return value.toFixed(digits)
}

/** Format drive time to Boston. */
export function formatCommute(minutes: number | null | undefined): string {
  if (minutes == null || Number.isNaN(minutes)) return EM_DASH
  return `${Math.round(minutes)} min`
}

/** Generic nullable formatter. */
export function formatNullable<T>(
  value: T | null | undefined,
  format: (v: T) => string,
): string {
  if (value == null) return EM_DASH
  return format(value)
}

export function sourceLabel(source: string | null | undefined): string {
  if (source === 'foundry_hosted_agent') return 'Foundry Hosted Agent'
  if (source === 'local_query_pipeline') return 'Local Query Pipeline'
  return 'Unknown'
}

export function backendModeLabel(mode: string | null | undefined): string {
  if (mode === 'foundry') return 'Foundry'
  if (mode === 'local') return 'Local'
  return mode ?? 'Unknown'
}
