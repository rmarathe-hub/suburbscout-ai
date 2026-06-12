import { useEffect, useState } from 'react'

import { LOADING_STEP_DELAYS_MS, LOADING_STEPS } from '@/lib/loadingSteps'

export function useLoadingSteps(active: boolean) {
  const [stepIndex, setStepIndex] = useState(0)

  useEffect(() => {
    if (!active) {
      setStepIndex(0)
      return
    }

    setStepIndex(0)
    const timers = LOADING_STEP_DELAYS_MS.map((delay, index) =>
      window.setTimeout(() => setStepIndex(index), delay),
    )

    return () => {
      timers.forEach((id) => window.clearTimeout(id))
    }
  }, [active])

  return {
    stepIndex,
    steps: LOADING_STEPS,
    currentLabel: LOADING_STEPS[stepIndex],
  }
}
