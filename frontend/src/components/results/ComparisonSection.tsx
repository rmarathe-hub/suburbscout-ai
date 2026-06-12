import { ComparisonPanel } from '@/components/results/ComparisonPanel'
import type { QueryResponse } from '@/api/types'
import { parseComparison } from '@/lib/comparison'
import { cn } from '@/lib/utils'

interface ComparisonSectionProps {
  isLoading: boolean
  response: QueryResponse | null
}

export function ComparisonSection({ isLoading, response }: ComparisonSectionProps) {
  const comparison = parseComparison(response?.comparison ?? null)

  return (
    <section
      aria-label="Town comparison"
      className={cn('md:col-span-2', isLoading && 'pointer-events-none opacity-60')}
    >
      <div className="mb-4">
        <h2 className="text-lg font-semibold tracking-tight">Side-by-side comparison</h2>
        <p className="text-sm text-muted-foreground">
          {isLoading
            ? 'Building comparison table…'
            : comparison
              ? `Comparing ${comparison.towns.join(' vs ')}`
              : 'Compare two or more towns to see metrics here'}
        </p>
      </div>

      <ComparisonPanel data={comparison} isLoading={isLoading} />
    </section>
  )
}
