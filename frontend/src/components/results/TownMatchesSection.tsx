import { TownGrid } from '@/components/results/TownGrid'
import type { QueryResponse } from '@/api/types'
import { parseTownMatches } from '@/lib/townMatch'
import { cn } from '@/lib/utils'

interface TownMatchesSectionProps {
  isLoading: boolean
  response: QueryResponse | null
}

export function TownMatchesSection({ isLoading, response }: TownMatchesSectionProps) {
  const towns = parseTownMatches(response?.top_matches)
  const count = towns.length

  return (
    <section
      aria-label="Town recommendations"
      className={cn('md:col-span-2', isLoading && 'pointer-events-none opacity-60')}
    >
      <div className="mb-4 flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">Top recommendations</h2>
          <p className="text-sm text-muted-foreground">
            {isLoading
              ? 'Ranking towns from the dataset…'
              : count > 0
                ? `${count} town${count === 1 ? '' : 's'} from your search`
                : 'Ranked matches appear for recommendation-style queries'}
          </p>
        </div>
      </div>

      <TownGrid towns={towns} isLoading={isLoading} />
    </section>
  )
}
