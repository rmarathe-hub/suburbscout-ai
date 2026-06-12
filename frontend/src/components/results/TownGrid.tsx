import { MapPinned } from 'lucide-react'

import { TownCard } from '@/components/results/TownCard'
import type { TownMatch } from '@/api/types'
import { cn } from '@/lib/utils'

interface TownGridProps {
  towns: TownMatch[]
  isLoading?: boolean
  className?: string
}

export function TownGrid({ towns, isLoading = false, className }: TownGridProps) {
  if (isLoading) {
    return (
      <div
        className={cn('grid gap-4 sm:grid-cols-2 xl:grid-cols-3', className)}
        aria-hidden
      >
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-44 animate-pulse rounded-xl bg-muted/60" />
        ))}
      </div>
    )
  }

  if (towns.length === 0) {
    return (
      <div
        className={cn(
          'flex flex-col items-center justify-center rounded-xl border border-dashed border-border/80 bg-muted/20 px-6 py-10 text-center',
          className,
        )}
      >
        <MapPinned className="mb-2 size-8 text-muted-foreground/60" aria-hidden />
        <p className="text-sm font-medium text-foreground">No ranked town matches</p>
        <p className="mt-1 max-w-sm text-sm text-muted-foreground">
          Commute and lookup questions often return an answer only. Try a ranking prompt like
          &ldquo;safe suburbs under $900k with good schools.&rdquo;
        </p>
      </div>
    )
  }

  return (
    <ul className={cn('grid list-none gap-4 sm:grid-cols-2 xl:grid-cols-3', className)}>
      {towns.map((town, index) => (
        <li key={`${town.name}-${index}`}>
          <TownCard town={town} rank={index + 1} />
        </li>
      ))}
    </ul>
  )
}
