import { Compass } from 'lucide-react'

import { AnswerCard } from '@/components/results/AnswerCard'
import { ComparisonSection } from '@/components/results/ComparisonSection'
import { TownMatchesSection } from '@/components/results/TownMatchesSection'
import { RefusalPanel } from '@/components/trust/RefusalPanel'
import { useLoadingSteps } from '@/hooks/useLoadingSteps'
import type { QueryResponse } from '@/api/types'
import { detectRefusal } from '@/lib/refusal'

interface ResultsSectionProps {
  isLoading: boolean
  response: QueryResponse | null
  isFoundryMode?: boolean
  hasSearched?: boolean
  onRetry?: () => void
}

export function ResultsSection({
  isLoading,
  response,
  isFoundryMode = false,
  hasSearched = false,
  onRetry,
}: ResultsSectionProps) {
  const { stepIndex } = useLoadingSteps(isLoading)
  const refusal = !isLoading ? detectRefusal(response) : null
  const showWelcome = !isLoading && !response && !hasSearched

  return (
    <section aria-label="Results" className="grid gap-6 md:grid-cols-2">
      {showWelcome && <WelcomeState />}

      {(isLoading || response || hasSearched) && (
        <>
          {refusal && <RefusalPanel refusal={refusal} onRetry={onRetry} className="md:col-span-2" />}

          <AnswerCard
            isLoading={isLoading}
            loadingStepIndex={stepIndex}
            response={response}
            isFoundryMode={isFoundryMode}
          />

          <TownMatchesSection isLoading={isLoading} response={response} />

          <ComparisonSection isLoading={isLoading} response={response} />
        </>
      )}
    </section>
  )
}

function WelcomeState() {
  return (
    <div className="md:col-span-2 flex flex-col items-center justify-center rounded-2xl border border-dashed border-border/80 bg-card/50 px-6 py-14 text-center shadow-[var(--shadow-card)]">
      <Compass className="mb-3 size-10 text-primary/70" aria-hidden />
      <h2 className="text-lg font-semibold text-foreground">Ready when you are</h2>
      <p className="mt-2 max-w-md text-sm text-muted-foreground">
        Pick a sample prompt above or type your own question. SuburbScout returns grounded answers
        from our 200-town dataset — not a generic chatbot.
      </p>
    </div>
  )
}
