import { AlertTriangle, Sparkles } from 'lucide-react'

import { AgentLoadingSteps } from '@/components/loading/AgentLoadingSteps'
import { SourceBadges } from '@/components/results/SourceBadges'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import type { QueryResponse } from '@/api/types'
import { cn } from '@/lib/utils'

interface AnswerCardProps {
  isLoading: boolean
  loadingStepIndex: number
  response: QueryResponse | null
  isFoundryMode?: boolean
}

const DEFAULT_SCORE_DISCLAIMER =
  'Scores are 0–10 percentile ranks within the 200-town dataset, not official government ratings.'

export function AnswerCard({
  isLoading,
  loadingStepIndex,
  response,
  isFoundryMode = false,
}: AnswerCardProps) {
  const showAnswer = !isLoading && response
  const isError =
    showAnswer &&
    (response.execution_status === 'error' ||
      response.error === 'foundry_agent_error')

  return (
    <Card className="overflow-hidden shadow-[var(--shadow-card)] md:col-span-2">
      <CardHeader className="border-b border-border/50 bg-card">
        <div className="flex items-start gap-2">
          <div className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Sparkles className="size-4" aria-hidden />
          </div>
          <div className="min-w-0 flex-1 space-y-1">
            <CardTitle className="text-lg">SuburbScout answer</CardTitle>
            <CardDescription>
              {isLoading
                ? 'Working on your question…'
                : showAnswer
                  ? subtitleForResponse(response)
                  : 'Ask a question to get a grounded recommendation'}
            </CardDescription>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-4 pt-5 text-sm">
        {isLoading && (
          <AgentLoadingSteps stepIndex={loadingStepIndex} isFoundryMode={isFoundryMode} />
        )}

        {!isLoading && !response && (
          <p className="rounded-xl bg-muted/40 px-4 py-10 text-center text-muted-foreground">
            Your grounded answer will appear here after you search.
          </p>
        )}

        {showAnswer && (
          <>
            <SourceBadges response={response} />

            <div
              className={cn(
                'rounded-xl border px-4 py-4 sm:px-5 sm:py-5',
                isError
                  ? 'border-destructive/25 bg-destructive/5'
                  : 'border-border/60 bg-background/80',
              )}
            >
              {response.answer ? (
                <AnswerBody text={response.answer} />
              ) : (
                <p className="text-muted-foreground">No answer text was returned.</p>
              )}
            </div>

            {response.tradeoff_warning && (
              <div
                className="flex gap-2 rounded-xl border border-amber-300/60 bg-amber-50 px-4 py-3 text-amber-950"
                role="note"
              >
                <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-600" aria-hidden />
                <p className="text-sm leading-relaxed">{response.tradeoff_warning}</p>
              </div>
            )}

            <p className="text-xs leading-relaxed text-muted-foreground">
              {response.score_disclaimer || DEFAULT_SCORE_DISCLAIMER}
            </p>

            {response.request_id && (
              <p className="font-mono text-[0.65rem] text-muted-foreground/80">
                Request {response.request_id}
              </p>
            )}
          </>
        )}
      </CardContent>
    </Card>
  )
}

function subtitleForResponse(response: QueryResponse): string {
  const parts: string[] = []
  if (response.latency_ms != null) {
    parts.push(`${(response.latency_ms / 1000).toFixed(1)}s`)
  }
  if (response.used_answer_llm) {
    parts.push('LLM narration')
  }
  return parts.length ? parts.join(' · ') : 'Grounded on suburbs.json'
}

function AnswerBody({ text }: { text: string }) {
  const paragraphs = text
    .split(/\n\s*\n/)
    .map((p) => p.trim())
    .filter(Boolean)

  if (paragraphs.length <= 1) {
    return <p className="whitespace-pre-wrap text-base leading-relaxed text-foreground">{text}</p>
  }

  return (
    <div className="space-y-3 text-base leading-relaxed text-foreground">
      {paragraphs.map((paragraph, index) => (
        <p key={index} className="whitespace-pre-wrap">
          {paragraph}
        </p>
      ))}
    </div>
  )
}
