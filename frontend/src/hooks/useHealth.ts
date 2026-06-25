import { useEffect, useState } from 'react'

import {
  ApiError,
  ensureFoundryWarm,
  getHealth,
  startFoundryWarmup,
} from '@/api/client'
import type { HealthResponse } from '@/api/types'

export type HealthState =
  | { status: 'loading'; message: string }
  | { status: 'warming'; message: string; data: HealthResponse }
  | { status: 'ok'; data: HealthResponse }
  | { status: 'error'; message: string }

const CONNECTING_MESSAGE = 'Connecting to server…'
const WAKING_MESSAGE = 'Waking up demo server…'
const WARMING_AGENT_MESSAGE = 'Starting query agent…'

function needsFoundryWarm(health: HealthResponse): boolean {
  return (
    health.backend_agent_mode === 'foundry' && Boolean(health.foundry_agent_configured)
  )
}

export function useHealth(): HealthState {
  const [state, setState] = useState<HealthState>({
    status: 'loading',
    message: CONNECTING_MESSAGE,
  })

  useEffect(() => {
    let cancelled = false

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
      .then(async (data) => {
        if (cancelled) return

        if (!needsFoundryWarm(data)) {
          setState({ status: 'ok', data })
          return
        }

        setState({
          status: 'warming',
          message: WARMING_AGENT_MESSAGE,
          data,
        })
        startFoundryWarmup()
        await ensureFoundryWarm()
        if (!cancelled) {
          setState({ status: 'ok', data })
        }
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

export function isBackendReady(health: HealthState): boolean {
  return health.status === 'ok'
}

export function isBackendBusy(health: HealthState): boolean {
  return health.status === 'loading' || health.status === 'warming'
}
