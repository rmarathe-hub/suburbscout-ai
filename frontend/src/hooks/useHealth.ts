import { useEffect, useState } from 'react'

import { ApiError, getHealth, warmupBackend } from '@/api/client'
import type { HealthResponse } from '@/api/types'

export type HealthState =
  | { status: 'loading'; message: string }
  | { status: 'ok'; data: HealthResponse }
  | { status: 'error'; message: string }

const CONNECTING_MESSAGE = 'Connecting to server…'
const WAKING_MESSAGE = 'Waking up demo server…'

export function useHealth(): HealthState {
  const [state, setState] = useState<HealthState>({
    status: 'loading',
    message: CONNECTING_MESSAGE,
  })

  useEffect(() => {
    let cancelled = false

    warmupBackend()

    const wakeTimer = window.setTimeout(() => {
      if (!cancelled) {
        setState((current) =>
          current.status === 'loading'
            ? { status: 'loading', message: WAKING_MESSAGE }
            : current,
        )
      }
    }, 2_500)

    getHealth()
      .then((data) => {
        if (!cancelled) setState({ status: 'ok', data })
      })
      .catch((error: unknown) => {
        if (cancelled) return
        const message =
          error instanceof ApiError
            ? error.message
            : error instanceof Error
              ? error.message
              : 'Health check failed'
        setState({
          status: 'error',
          message: `Could not reach the API after several attempts. ${message}`,
        })
      })

    return () => {
      cancelled = true
      window.clearTimeout(wakeTimer)
    }
  }, [])

  return state
}
