import { MapPin } from 'lucide-react'

import { BackendStatus } from '@/components/layout/BackendStatus'

export function Header() {
  return (
    <header className="sticky top-0 z-50 border-b border-border/70 bg-card/90 shadow-sm backdrop-blur-md">
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-3 sm:px-6 sm:py-4">
        <div className="flex min-w-0 items-center gap-3">
          <div
            className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-[var(--shadow-card)]"
            aria-hidden
          >
            <MapPin className="size-5" />
          </div>
          <div className="min-w-0 text-left">
            <p className="truncate text-base font-semibold tracking-tight">SuburbScout</p>
            <p className="truncate text-xs text-muted-foreground sm:text-sm">
              Boston suburb intelligence · grounded AI
            </p>
          </div>
        </div>
        <BackendStatus />
      </div>
    </header>
  )
}
