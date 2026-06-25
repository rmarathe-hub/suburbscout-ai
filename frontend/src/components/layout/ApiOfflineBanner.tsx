import { AlertCircle } from 'lucide-react'

import { Button } from '@/components/ui/button'

interface ApiOfflineBannerProps {
  message: string
  onRetry?: () => void
  isRetrying?: boolean
}

export function ApiOfflineBanner({
  message,
  onRetry,
  isRetrying = false,
}: ApiOfflineBannerProps) {
  return (
    <div
      role="alert"
      className="border-b border-destructive/30 bg-destructive/10 px-4 py-2.5 text-sm text-destructive"
    >
      <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 sm:px-2">
        <div className="flex min-w-0 items-start gap-2">
          <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden />
          <p>
            <span className="font-medium">API unreachable.</span> {message} The demo server may
            still be waking up.
          </p>
        </div>
        {onRetry && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onRetry}
            disabled={isRetrying}
            className="shrink-0 border-destructive/40 text-destructive hover:bg-destructive/10"
          >
            {isRetrying ? 'Reconnecting…' : 'Retry connection'}
          </Button>
        )}
      </div>
    </div>
  )
}
