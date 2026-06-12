import { Clock, History, Loader2 } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import type { SavedSearchesState } from '@/hooks/useSavedSearches'
import type { SearchSummary } from '@/api/types'
import { cn } from '@/lib/utils'

interface SavedSearchesProps {
  state: SavedSearchesState
  activeRequestId?: string | null
  loadingRequestId?: string | null
  onSelect: (search: SearchSummary) => void
  onRefresh?: () => void
}

export function SavedSearches({
  state,
  activeRequestId,
  loadingRequestId,
  onSelect,
  onRefresh,
}: SavedSearchesProps) {
  return (
    <Card className="shadow-[var(--shadow-card)]">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Clock className="size-4 text-muted-foreground" aria-hidden />
            <CardTitle className="text-base">Saved searches</CardTitle>
          </div>
          {onRefresh && state.status !== 'loading' && (
            <Button type="button" variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={onRefresh}>
              Refresh
            </Button>
          )}
        </div>
        <CardDescription>
          Click a row to reload that result from the database (no new API query).
        </CardDescription>
      </CardHeader>
      <CardContent>
        {state.status === 'loading' && (
          <div className="space-y-2" aria-hidden>
            <div className="h-10 animate-pulse rounded-lg bg-muted/60" />
            <div className="h-10 animate-pulse rounded-lg bg-muted/60" />
          </div>
        )}

        {state.status === 'unavailable' && (
          <p className="text-sm text-muted-foreground">
            History unavailable — the API needs <span className="font-mono text-xs">DATABASE_URL</span>{' '}
            configured.
          </p>
        )}

        {state.status === 'ok' && state.searches.length === 0 && (
          <div className="flex flex-col items-center py-4 text-center text-sm text-muted-foreground">
            <History className="mb-2 size-6 opacity-50" aria-hidden />
            <p>Run a search to see history here.</p>
          </div>
        )}

        {state.status === 'ok' && state.searches.length > 0 && (
          <ul className="max-h-[320px] space-y-1 overflow-y-auto">
            {state.searches.map((search) => {
              const isLoadingRow = loadingRequestId === search.request_id
              return (
              <li key={search.request_id}>
                <button
                  type="button"
                  disabled={Boolean(loadingRequestId)}
                  onClick={() => onSelect(search)}
                  className={cn(
                    'w-full rounded-lg border px-3 py-2.5 text-left text-sm transition-colors',
                    'hover:border-primary/30 hover:bg-muted/50',
                    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40',
                    'disabled:cursor-not-allowed disabled:opacity-60',
                    activeRequestId === search.request_id
                      ? 'border-primary/40 bg-primary/5'
                      : 'border-transparent bg-muted/30',
                  )}
                >
                  <p className="line-clamp-2 font-medium text-foreground">{search.prompt}</p>
                  <div className="mt-1.5 flex flex-wrap items-center gap-2">
                    {search.execution_status && (
                      <Badge variant="outline" className="text-[0.65rem] font-normal">
                        {search.execution_status}
                      </Badge>
                    )}
                    {search.created_at && (
                      <span className="text-xs text-muted-foreground">
                        {formatRelativeTime(search.created_at)}
                      </span>
                    )}
                    {isLoadingRow && (
                      <Loader2 className="size-3 motion-safe:animate-spin text-muted-foreground" aria-hidden />
                    )}
                  </div>
                </button>
              </li>
            )})}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}

function formatRelativeTime(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  const diffMs = Date.now() - date.getTime()
  const minutes = Math.floor(diffMs / 60_000)
  if (minutes < 1) return 'Just now'
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return date.toLocaleDateString()
}
