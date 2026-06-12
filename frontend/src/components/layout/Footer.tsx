import { getApiBaseUrl } from '@/api/client'

const SCORE_DISCLAIMER =
  'Scores are 0–10 percentile ranks within our 200-town dataset, not official government ratings.'

export function Footer() {
  return (
    <footer className="mt-auto border-t border-border/60 bg-card/50">
      <div className="mx-auto max-w-7xl space-y-4 px-4 py-6 sm:px-6">
        <details className="group rounded-xl border border-border/80 bg-background/80 px-4 py-3 shadow-[var(--shadow-card)]">
          <summary className="cursor-pointer list-none text-sm font-medium text-foreground marker:content-none [&::-webkit-details-marker]:hidden">
            <span className="inline-flex items-center gap-2">
              Why this answer?
              <span className="text-xs font-normal text-muted-foreground group-open:hidden">
                Tap to learn about our data
              </span>
            </span>
          </summary>
          <ul className="mt-3 space-y-2 border-t border-border/60 pt-3 text-sm text-muted-foreground">
            <li>Answers use a curated dataset of 200 Boston-area towns.</li>
            <li>{SCORE_DISCLAIMER}</li>
            <li>Commute times are measured to South Station, Boston.</li>
            <li>We do not use live Zillow, Redfin, or MLS listing feeds.</li>
          </ul>
        </details>

        <div className="flex flex-col gap-1 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
          <p>SuburbScout · Phase 8 dashboard</p>
          <p className="font-mono text-[0.7rem]">{getApiBaseUrl()}</p>
        </div>
      </div>
    </footer>
  )
}
