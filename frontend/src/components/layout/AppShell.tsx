import type { ReactNode } from 'react'

import { Footer } from '@/components/layout/Footer'
import { Header } from '@/components/layout/Header'
import type { HealthState } from '@/hooks/useHealth'

interface AppShellProps {
  children: ReactNode
  sidebar?: ReactNode
  banner?: ReactNode
  health: HealthState
}

export function AppShell({ children, sidebar, banner, health }: AppShellProps) {
  return (
    <div className="flex min-h-svh flex-col bg-[linear-gradient(180deg,hsl(var(--background))_0%,hsl(214_45%_95%)_42%,hsl(210_40%_98%)_100%)]">
      <Header health={health} />
      {banner}

      <div className="mx-auto w-full max-w-7xl flex-1 px-4 py-8 sm:px-6 sm:py-10">
        <div className="grid grid-cols-1 gap-8 lg:grid-cols-[minmax(0,1fr)_300px] lg:gap-10 xl:grid-cols-[minmax(0,1fr)_320px]">
          <main className="min-w-0 space-y-8">{children}</main>
          {sidebar}
        </div>
      </div>

      <Footer />
    </div>
  )
}
