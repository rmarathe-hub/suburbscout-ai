import { useCallback, useEffect, useState, type Dispatch, type SetStateAction } from 'react'

import {
  ApiError,
  ensureFoundryWarm,
  getHealth,
  resetFoundryWarmup,
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

async function runHealthCheck(
  setState: Dispatch<SetStateAction<HealthState>>,
  cancelled: () => boolean,
): Promise<void> {
  const wakeTimer = window.setTimeout(() => {
    if (!cancelled()) {
      setState((current) =>
        current.status === 'loading'
          ? { status: 'loading', message: WAKING_MESSAGE }
          : current,
      )
    }
  }, 2_500)

  try {
    const data = await getHealth()
    if (cancelled()) return

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
    if (!cancelled()) {
      setState({ status: 'ok', data })
    }
  } catch (error: unknown) {
    if (cancelled()) return
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
  } finally {
    window.clearTimeout(wakeTimer)
  }
}

export function useHealth(): { health: HealthState; retry: () => void } {
  const [health, setHealth] = useState<HealthState>({
    status: 'loading',
    message: CONNECTING_MESSAGE,
  })
  const [attempt, setAttempt] = useState(0)

  const retry = useCallback(() => {
    resetFoundryWarmup()
    setHealth({ status: 'loading', message: CONNECTING_MESSAGE })
    setAttempt((count) => count + 1)
  }, [])

  useEffect(() => {
    let cancelled = false
    void runHealthCheck(setHealth, () => cancelled)
    return () => {
      cancelled = true
    }
  }, [attempt])

  return { health, retry }
}

export function isBackendReady(health: HealthState): boolean {
  return health.status === 'ok'
}

export function isBackendBusy(health: HealthState): boolean {
  return health.status === 'loading' || health.status === 'warming'
}
