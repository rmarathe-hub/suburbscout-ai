import { AlertCircle } from 'lucide-react'

interface ApiOfflineBannerProps {
  message: string
}

export function ApiOfflineBanner({ message }: ApiOfflineBannerProps) {
  return (
    <div
      role="alert"
      className="border-b border-destructive/30 bg-destructive/10 px-4 py-2.5 text-sm text-destructive"
    >
      <div className="mx-auto flex max-w-7xl items-start gap-2 sm:px-2">
        <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden />
        <p>
          <span className="font-medium">API unreachable.</span> {message} The demo server may still
          be waking up — try your search again in a moment.
        </p>
      </div>
    </div>
  )
}
