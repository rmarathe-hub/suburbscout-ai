import { useCallback, useRef, useState } from 'react'

import { ApiError, ensureFoundryWarm, getSearch, postQuery } from '@/api/client'
import type { QueryResponse, SearchSummary } from '@/api/types'
import { traceToQueryResponse } from '@/lib/searchTrace'

export interface SearchState {
  prompt: string
  isLoading: boolean
  loadingMessage: string | null
  loadingRequestId: string | null
  error: string | null
  response: QueryResponse | null
  hasSearched: boolean
}

function readErrorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message
  if (err instanceof Error) return err.message
  return 'Search failed. Please try again.'
}

export function useSearch(
  onSuccess?: (response: QueryResponse) => void,
  options: { isFoundryMode?: boolean; backendReady?: boolean } = {},
) {
  const { isFoundryMode = false, backendReady = true } = options
  const [prompt, setPrompt] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [loadingMessage, setLoadingMessage] = useState<string | null>(null)
  const [loadingRequestId, setLoadingRequestId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [response, setResponse] = useState<QueryResponse | null>(null)
  const [hasSearched, setHasSearched] = useState(false)
  const responseCache = useRef<Map<string, QueryResponse>>(new Map())

  const cacheResponse = useCallback((result: QueryResponse) => {
    if (result.request_id) {
      responseCache.current.set(result.request_id, result)
    }
  }, [])

  const runQuery = useCallback(
    async (query: string) => {
      const result = await postQuery(query, { saveAudit: true })
      cacheResponse(result)
      setResponse(result)
      onSuccess?.(result)
      return result
    },
    [cacheResponse, onSuccess],
  )

  const submit = useCallback(
    async (text?: string) => {
      const query = (text ?? prompt).trim()
      if (!query || isLoading || !backendReady) return

      setPrompt(query)
      setIsLoading(true)
      setLoadingMessage('Connecting to server…')
      setLoadingRequestId(null)
      setError(null)
      setResponse(null)
      setHasSearched(true)

      const wakeTimer = window.setTimeout(() => {
        setLoadingMessage((current) => {
          if (current === 'Connecting to server…') return 'Waking up demo server…'
          if (current === 'Waking up demo server…') return 'Starting query agent…'
          return current
        })
      }, 2_500)

      const agentTimer = window.setTimeout(() => {
        setLoadingMessage((current) =>
          current === 'Starting query agent…' ? 'Running your query…' : current,
        )
      }, 12_000)

      try {
        if (isFoundryMode) {
          setLoadingMessage('Starting query agent…')
          await ensureFoundryWarm()
        }
        setLoadingMessage('Running your query…')
        await runQuery(query)
      } catch (err) {
        setResponse(null)
        setError(readErrorMessage(err))
      } finally {
        window.clearTimeout(wakeTimer)
        window.clearTimeout(agentTimer)
        setIsLoading(false)
        setLoadingMessage(null)
      }
    },
    [prompt, isLoading, runQuery, isFoundryMode, backendReady],
  )

  const loadSavedSearch = useCallback(
    async (search: SearchSummary) => {
      if (isLoading || !backendReady) return

      setPrompt(search.prompt)
      setHasSearched(true)
      setError(null)

      const cached = responseCache.current.get(search.request_id)
      if (cached) {
        setResponse(cached)
        return
      }

      setIsLoading(true)
      setLoadingRequestId(search.request_id)
      setResponse(null)

      let fallbackToLiveQuery = false
      try {
        const trace = await getSearch(search.request_id)
        const restored = traceToQueryResponse(trace)
        cacheResponse(restored)
        setResponse(restored)
      } catch (err) {
        if (err instanceof ApiError && (err.status === 404 || err.status === 503)) {
          fallbackToLiveQuery = true
        } else {
          setError(readErrorMessage(err))
        }
      } finally {
        setIsLoading(false)
        setLoadingRequestId(null)
      }

      if (fallbackToLiveQuery) {
        setIsLoading(true)
        setLoadingMessage('Connecting to server…')
        try {
          if (isFoundryMode) {
            await ensureFoundryWarm()
          }
          await runQuery(search.prompt)
        } catch (err) {
          setResponse(null)
          setError(readErrorMessage(err))
        } finally {
          setIsLoading(false)
          setLoadingMessage(null)
        }
      }
    },
    [isLoading, cacheResponse, runQuery, backendReady, isFoundryMode],
  )

  const clearError = useCallback(() => setError(null), [])

  return {
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
    clearError,
  }
}
