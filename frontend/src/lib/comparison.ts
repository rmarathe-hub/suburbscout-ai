import type { ComparisonColumn, ComparisonData, ComparisonRow } from '@/api/types'

const DEFAULT_COLUMNS: ComparisonColumn[] = [
  { key: 'latest_home_price', label: 'Home price' },
  { key: 'drive_minutes_to_boston', label: 'Commute' },
  { key: 'safety_score', label: 'Safety' },
  { key: 'school_score', label: 'Schools' },
]

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

function parseColumns(raw: Record<string, unknown>): ComparisonColumn[] {
  const cols = raw.columns
  if (!Array.isArray(cols) || cols.length === 0) return DEFAULT_COLUMNS

  return cols
    .map((col) => {
      if (!col || typeof col !== 'object') return null
      const c = col as Record<string, unknown>
      const key = typeof c.key === 'string' ? c.key : typeof c.alias === 'string' ? c.alias : null
      const label = typeof c.label === 'string' ? c.label : key
      if (!key || !label) return null
      return { key, label }
    })
    .filter((c): c is ComparisonColumn => c !== null)
}

function parseComparisonTable(
  table: unknown,
  columns: ComparisonColumn[],
): ComparisonRow[] {
  if (!Array.isArray(table)) return []

  return table
    .map((row) => {
      const r = asRecord(row)
      if (!r) return null
      const town = typeof r.town === 'string' ? r.town : null
      if (!town) return null

      const values: Record<string, number | string | boolean | null> = {}
      for (const col of columns) {
        const v = r[col.key]
        if (v === null || v === undefined) {
          values[col.key] = null
        } else if (typeof v === 'number' || typeof v === 'string' || typeof v === 'boolean') {
          values[col.key] = v
        }
      }
      return { town, values }
    })
    .filter((r): r is ComparisonRow => r !== null)
}

function parseTownPair(raw: Record<string, unknown>): ComparisonData | null {
  const townA = asRecord(raw.town_a)
  const townB = asRecord(raw.town_b)
  if (!townA || !townB) return null

  const nameA = typeof townA.town === 'string' ? townA.town : typeof townA.name === 'string' ? townA.name : 'Town A'
  const nameB = typeof townB.town === 'string' ? townB.town : typeof townB.name === 'string' ? townB.name : 'Town B'

  const columns = DEFAULT_COLUMNS
  const rowFromTown = (name: string, town: Record<string, unknown>): ComparisonRow => ({
    town: name,
    values: Object.fromEntries(
      columns.map((col) => [col.key, (town[col.key] as number | string | null) ?? null]),
    ),
  })

  return {
    rows: [rowFromTown(nameA, townA), rowFromTown(nameB, townB)],
    columns,
    towns: [nameA, nameB],
    errors: asStringArray(raw.errors),
  }
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.filter((item): item is string => typeof item === 'string')
}

/** Normalize comparison payload from QueryResponse.comparison. */
export function parseComparison(raw: Record<string, unknown> | null | undefined): ComparisonData | null {
  if (!raw) return null

  if (raw.comparison_table || raw.columns) {
    const columns = parseColumns(raw)
    const rows = parseComparisonTable(raw.comparison_table, columns)
    if (rows.length === 0) return null
    return {
      rows,
      columns,
      towns: asStringArray(raw.towns).length ? asStringArray(raw.towns) : rows.map((r) => r.town),
      errors: asStringArray(raw.errors),
    }
  }

  return parseTownPair(raw)
}
