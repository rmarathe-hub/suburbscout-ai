import { Loader2, Search } from 'lucide-react'
import type { FormEvent } from 'react'

import { Button } from '@/components/ui/button'
import { PromptChips } from '@/components/search/PromptChips'
import { SEARCH_PLACEHOLDER } from '@/lib/prompts'
import { cn } from '@/lib/utils'

interface HeroSearchProps {
  prompt: string
  onPromptChange: (value: string) => void
  onSubmit: (prompt?: string) => void
  isLoading?: boolean
  isSubmitDisabled?: boolean
  submitHint?: string | null
  error?: string | null
}

export function HeroSearch({
  prompt,
  onPromptChange,
  onSubmit,
  isLoading = false,
  isSubmitDisabled = false,
  submitHint = null,
  error = null,
}: HeroSearchProps) {
  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    onSubmit()
  }

  const submitBlocked = isLoading || isSubmitDisabled || !prompt.trim()

  const handleChipSelect = (text: string) => {
    if (isSubmitDisabled) return
    onPromptChange(text)
    onSubmit(text)
  }

  return (
    <section aria-label="Search suburbs" className="space-y-5">
      <div className="mx-auto max-w-3xl text-center lg:mx-0 lg:max-w-none lg:text-left">
        <h1 className="text-3xl font-semibold tracking-tight text-foreground sm:text-4xl lg:text-[2.5rem] lg:leading-tight">
          Find Boston suburbs that match your lifestyle
        </h1>
        <p className="mt-3 max-w-2xl text-base text-muted-foreground sm:text-lg">
          Ask in plain English — schools, safety, commute, price, or side-by-side town
          comparisons.
        </p>
      </div>

      <form
        onSubmit={handleSubmit}
        className="rounded-2xl border border-border/80 bg-card p-4 shadow-[var(--shadow-card)] sm:p-5"
      >
        <label htmlFor="suburb-search" className="sr-only">
          Search suburbs
        </label>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="relative min-w-0 flex-1">
            <Search
              className="pointer-events-none absolute top-1/2 left-3.5 size-5 -translate-y-1/2 text-muted-foreground"
              aria-hidden
            />
            <input
              id="suburb-search"
              type="text"
              value={prompt}
              onChange={(e) => onPromptChange(e.target.value)}
              placeholder={SEARCH_PLACEHOLDER}
              disabled={isLoading || isSubmitDisabled}
              autoComplete="off"
              maxLength={4000}
              className={cn(
                'h-12 w-full rounded-xl border border-input bg-background pr-4 pl-11 text-base text-foreground',
                'placeholder:text-muted-foreground/80',
                'outline-none transition-shadow focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30',
                'disabled:cursor-not-allowed disabled:opacity-60',
              )}
            />
          </div>
          <Button
            type="submit"
            size="lg"
            disabled={submitBlocked}
            className="h-12 shrink-0 rounded-xl px-6 sm:min-w-[120px]"
          >
            {isLoading ? (
              <>
                <Loader2 className="size-4 motion-safe:animate-spin" aria-hidden />
                Searching…
              </>
            ) : isSubmitDisabled ? (
              'Please wait…'
            ) : (
              'Search'
            )}
          </Button>
        </div>

        {submitHint && !isLoading && (
          <p className="mt-3 text-sm text-muted-foreground" role="status">
            {submitHint}
          </p>
        )}

        {error && (
          <p className="mt-3 text-sm text-destructive" role="alert">
            {error}
          </p>
        )}
      </form>

      <PromptChips onSelect={handleChipSelect} disabled={isLoading || isSubmitDisabled} />
    </section>
  )
}
