import { useCallback, useState } from 'react'

import { AppShell } from '@/components/layout/AppShell'
import { ApiOfflineBanner } from '@/components/layout/ApiOfflineBanner'
import { Sidebar } from '@/components/layout/Sidebar'
import { ResultsSection } from '@/components/results/ResultsSection'
import { HeroSearch } from '@/components/search/HeroSearch'
import { useHealth } from '@/hooks/useHealth'
import { useSavedSearches } from '@/hooks/useSavedSearches'
import { useSearch } from '@/hooks/useSearch'
import type { SearchSummary } from '@/api/types'

export default function App() {
  const health = useHealth()
  const [searchRefreshKey, setSearchRefreshKey] = useState(0)
  const savedSearches = useSavedSearches(searchRefreshKey)

  const handleQuerySuccess = useCallback(() => {
    setSearchRefreshKey((k) => k + 1)
  }, [])

  const {
    prompt,
    setPrompt,
    submit,
    loadSavedSearch,
    isLoading,
    loadingMessage,
    loadingRequestId,
    error,
    response,
    hasSearched,
  } = useSearch(handleQuerySuccess)

  const isFoundryMode =
    health.status === 'ok' && health.data.backend_agent_mode === 'foundry'

  const handleSelectSearch = useCallback(
    (search: SearchSummary) => {
      void loadSavedSearch(search)
    },
    [loadSavedSearch],
  )

  const handleRetry = useCallback(() => {
    if (prompt.trim()) submit(prompt)
  }, [prompt, submit])

  return (
    <AppShell
      sidebar={
        <Sidebar
          savedSearches={savedSearches.state}
          activeRequestId={response?.request_id}
          loadingRequestId={loadingRequestId}
          onSelectSearch={handleSelectSearch}
          onRefreshSearches={savedSearches.refresh}
        />
      }
      banner={
        health.status === 'error' ? <ApiOfflineBanner message={health.message} /> : null
      }
    >
      <HeroSearch
        prompt={prompt}
        onPromptChange={setPrompt}
        onSubmit={submit}
        isLoading={isLoading}
        error={error}
      />

      <ResultsSection
        isLoading={isLoading}
        loadingMessage={loadingMessage}
        response={response}
        isFoundryMode={isFoundryMode}
        hasSearched={hasSearched}
        onRetry={handleRetry}
      />
    </AppShell>
  )
}
