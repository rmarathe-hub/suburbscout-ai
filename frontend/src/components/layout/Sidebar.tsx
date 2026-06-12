import { SavedSearches } from '@/components/sidebar/SavedSearches'
import { TrustPanel } from '@/components/trust/TrustPanel'
import type { SavedSearchesState } from '@/hooks/useSavedSearches'
import type { SearchSummary } from '@/api/types'

interface SidebarProps {
  savedSearches: SavedSearchesState
  activeRequestId?: string | null
  loadingRequestId?: string | null
  onSelectSearch?: (search: SearchSummary) => void
  onRefreshSearches?: () => void
}

export function Sidebar({
  savedSearches,
  activeRequestId,
  loadingRequestId,
  onSelectSearch,
  onRefreshSearches,
}: SidebarProps) {
  return (
    <aside className="flex flex-col gap-4 lg:sticky lg:top-24 lg:self-start">
      <TrustPanel />
      <SavedSearches
        state={savedSearches}
        activeRequestId={activeRequestId}
        loadingRequestId={loadingRequestId}
        onSelect={(search) => onSelectSearch?.(search)}
        onRefresh={onRefreshSearches}
      />
    </aside>
  )
}
