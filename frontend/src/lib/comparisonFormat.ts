import type { ComparisonColumn } from '@/api/types'
import { formatCommute, formatPrice, formatScore } from '@/lib/format'

/** Format a comparison cell for display. */
export function formatComparisonValue(
  key: string,
  value: number | string | boolean | null | undefined,
): string {
  if (value == null) return '—'
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (typeof value === 'string') return value

  if (key === 'latest_home_price' || key.includes('price')) return formatPrice(value)
  if (key === 'drive_minutes_to_boston' || key.includes('commute') || key.includes('minutes')) {
    return formatCommute(value)
  }
  if (key.includes('score') || key.includes('safety') || key.includes('school')) {
    return formatScore(value)
  }
  return Number.isInteger(value) ? String(value) : value.toFixed(1)
}

/** Whether a higher numeric value is better for this metric. */
export function higherIsBetter(key: string): boolean {
  if (key === 'latest_home_price' || key.includes('price')) return false
  if (key === 'drive_minutes_to_boston' || key.includes('commute') || key.includes('minutes')) {
    return false
  }
  return true
}

export interface ColumnWinner {
  column: ComparisonColumn
  town: string
  label: string
}

/** Pick the winning town per numeric column (for 2+ row tables). */
export function computeColumnWinners(
  columns: ComparisonColumn[],
  rows: { town: string; values: Record<string, number | string | boolean | null> }[],
): ColumnWinner[] {
  const winners: ColumnWinner[] = []

  for (const column of columns) {
    const numeric = rows
      .map((row) => ({
        town: row.town,
        value: row.values[column.key],
      }))
      .filter((item): item is { town: string; value: number } => typeof item.value === 'number')

    if (numeric.length < 2) continue

    const best = higherIsBetter(column.key)
      ? numeric.reduce((a, b) => (b.value > a.value ? b : a))
      : numeric.reduce((a, b) => (b.value < a.value ? b : a))

    winners.push({
      column,
      town: best.town,
      label: column.label,
    })
  }

  return winners
}
