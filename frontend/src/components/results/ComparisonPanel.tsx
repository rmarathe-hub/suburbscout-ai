import { GitCompare } from 'lucide-react'

import type { ComparisonData } from '@/api/types'
import {
  computeColumnWinners,
  formatComparisonValue,
} from '@/lib/comparisonFormat'
import { cn } from '@/lib/utils'

interface ComparisonPanelProps {
  data: ComparisonData | null
  isLoading?: boolean
  className?: string
}

export function ComparisonPanel({ data, isLoading = false, className }: ComparisonPanelProps) {
  if (isLoading) {
    return (
      <div className={cn('space-y-3', className)} aria-hidden>
        <div className="h-5 w-40 animate-pulse rounded bg-muted" />
        <div className="h-32 animate-pulse rounded-xl bg-muted/60" />
      </div>
    )
  }

  if (!data || data.rows.length === 0) {
    return (
      <div
        className={cn(
          'flex flex-col items-center justify-center rounded-xl border border-dashed border-border/80 bg-muted/20 px-6 py-10 text-center',
          className,
        )}
      >
        <GitCompare className="mb-2 size-8 text-muted-foreground/60" aria-hidden />
        <p className="text-sm font-medium text-foreground">No comparison data</p>
        <p className="mt-1 max-w-sm text-sm text-muted-foreground">
          Try a compare prompt like &ldquo;Compare Acton and Burlington.&rdquo;
        </p>
      </div>
    )
  }

  const winners = computeColumnWinners(data.columns, data.rows)

  return (
    <div className={cn('space-y-4', className)}>
      {winners.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {winners.map((winner) => (
            <span
              key={winner.column.key}
              className="inline-flex items-center gap-1.5 rounded-full border border-primary/15 bg-primary/5 px-3 py-1 text-xs text-primary"
            >
              <span className="text-muted-foreground">Best {winner.label.toLowerCase()}:</span>
              <span className="font-medium">{winner.town}</span>
            </span>
          ))}
        </div>
      )}

      <div className="-mx-1 overflow-x-auto">
        <table className="w-full min-w-[320px] border-collapse text-sm">
          <thead>
            <tr className="border-b border-border/80">
              <th className="sticky left-0 bg-card px-3 py-2.5 text-left font-medium text-muted-foreground">
                Town
              </th>
              {data.columns.map((col) => (
                <th
                  key={col.key}
                  className="px-3 py-2.5 text-right font-medium text-muted-foreground whitespace-nowrap"
                >
                  {col.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row) => (
              <tr key={row.town} className="border-b border-border/50 last:border-0">
                <td className="sticky left-0 bg-card px-3 py-3 font-medium text-foreground">
                  {row.town}
                </td>
                {data.columns.map((col) => {
                  const raw = row.values[col.key]
                  const formatted = formatComparisonValue(col.key, raw)
                  const isWinner = winners.some(
                    (w) => w.column.key === col.key && w.town === row.town,
                  )
                  return (
                    <td
                      key={col.key}
                      className={cn(
                        'px-3 py-3 text-right tabular-nums whitespace-nowrap',
                        isWinner && 'font-semibold text-primary',
                      )}
                    >
                      {formatted}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {data.errors.length > 0 && (
        <ul className="space-y-1 text-xs text-amber-800">
          {data.errors.map((err, i) => (
            <li key={i}>{err}</li>
          ))}
        </ul>
      )}
    </div>
  )
}
