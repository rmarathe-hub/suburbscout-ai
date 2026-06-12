import { Ban, RefreshCw } from 'lucide-react'

import { Button } from '@/components/ui/button'
import type { RefusalInfo } from '@/lib/refusal'
import { cn } from '@/lib/utils'

interface RefusalPanelProps {
  refusal: RefusalInfo
  onRetry?: () => void
  className?: string
}

export function RefusalPanel({ refusal, onRetry, className }: RefusalPanelProps) {
  const isRetryable = refusal.kind === 'foundry_error'

  return (
    <div
      role="status"
      className={cn(
        'rounded-xl border border-amber-300/70 bg-amber-50/90 px-4 py-4 text-amber-950 sm:px-5',
        className,
      )}
    >
      <div className="flex gap-3">
        <Ban className="mt-0.5 size-5 shrink-0 text-amber-600" aria-hidden />
        <div className="min-w-0 flex-1 space-y-2">
          <p className="font-medium">{refusal.title}</p>
          <p className="text-sm leading-relaxed text-amber-900/90">{refusal.message}</p>
          {isRetryable && onRetry && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="mt-1 border-amber-400/60 bg-white/60 hover:bg-white"
              onClick={onRetry}
            >
              <RefreshCw className="size-3.5" aria-hidden />
              Try again
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}
