import { Check, Loader2 } from 'lucide-react'

import { LOADING_STEPS } from '@/lib/loadingSteps'
import { cn } from '@/lib/utils'

interface AgentLoadingStepsProps {
  stepIndex: number
  isFoundryMode?: boolean
  className?: string
}

export function AgentLoadingSteps({
  stepIndex,
  isFoundryMode = false,
  className,
}: AgentLoadingStepsProps) {
  return (
    <div
      className={cn('space-y-4', className)}
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <ul className="space-y-3">
        {LOADING_STEPS.map((label, index) => {
          const isComplete = index < stepIndex
          const isCurrent = index === stepIndex
          const isPending = index > stepIndex

          return (
            <li
              key={label}
              className={cn(
                'flex items-center gap-3 text-sm transition-opacity duration-300',
                isPending && 'opacity-40',
                isCurrent && 'font-medium text-foreground',
                isComplete && 'text-muted-foreground',
              )}
            >
              <span
                className={cn(
                  'flex size-7 shrink-0 items-center justify-center rounded-full border',
                  isComplete && 'border-accent/30 bg-accent/10 text-accent',
                  isCurrent && 'border-primary/30 bg-primary/10 text-primary',
                  isPending && 'border-border bg-muted/50 text-muted-foreground',
                )}
                aria-hidden
              >
                {isComplete ? (
                  <Check className="size-3.5" />
                ) : isCurrent ? (
                  <Loader2 className="size-3.5 motion-safe:animate-spin" />
                ) : (
                  <span className="size-1.5 rounded-full bg-muted-foreground/40" />
                )}
              </span>
              <span>{label}</span>
            </li>
          )
        })}
      </ul>

      {isFoundryMode && (
        <p className="rounded-lg border border-primary/15 bg-primary/5 px-3 py-2 text-xs text-muted-foreground">
          The demo server and cloud query agent may take up to two minutes on first load
          after idle time. Your search will start automatically once both are ready.
        </p>
      )}
    </div>
  )
}
