import { useCallback, useEffect, useState } from 'react'

import { ApiError, listSearches } from '@/api/client'
import type { SearchSummary } from '@/api/types'

export type SavedSearchesState =
  | { status: 'loading' }
  | { status: 'ok'; searches: SearchSummary[] }
  | { status: 'unavailable'; message: string }

export function useSavedSearches(refreshKey = 0) {
  const [state, setState] = useState<SavedSearchesState>({ status: 'loading' })

  const refresh = useCallback(() => {
    setState({ status: 'loading' })
    listSearches(10)
      .then((data) => setState({ status: 'ok', searches: data.searches }))
      .catch((error: unknown) => {
        const message =
          error instanceof ApiError
            ? error.message
            : error instanceof Error
              ? error.message
              : 'Could not load saved searches'
        setState({ status: 'unavailable', message })
      })
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh, refreshKey])

  return { state, refresh }
}
