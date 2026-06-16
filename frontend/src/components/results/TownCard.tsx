import { Car, DollarSign, GraduationCap, Shield } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { TownMatch } from '@/api/types'
import { formatCommute, formatPrice, formatScore } from '@/lib/format'
import { cn } from '@/lib/utils'

interface TownCardProps {
  town: TownMatch
  rank?: number
  className?: string
}

export function TownCard({ town, rank, className }: TownCardProps) {
  const matchReason = town.reasons[0] || town.tradeoffs[0]

  return (
    <Card
      className={cn(
        'shadow-[var(--shadow-card)] transition-shadow hover:shadow-[var(--shadow-card-hover)]',
        className,
      )}
    >
      <CardHeader className="flex flex-row items-start justify-between gap-2 space-y-0 pb-2">
        <div className="min-w-0">
          {rank != null && (
            <p className="text-xs font-medium text-muted-foreground">#{rank}</p>
          )}
          <CardTitle className="truncate text-base leading-snug">{town.name}</CardTitle>
          {town.dataQualityTier === 'partial' && (
            <Badge variant="outline" className="mt-1.5 text-[0.65rem] text-muted-foreground">
              Partial data
            </Badge>
          )}
        </div>
        {town.score != null && (
          <Badge className="shrink-0 bg-primary/10 text-primary hover:bg-primary/10">
            {formatScore(town.score, 2)}/10
          </Badge>
        )}
      </CardHeader>

      <CardContent className="space-y-3">
        <div className="flex flex-wrap gap-2">
          <MetricPill
            icon={DollarSign}
            label="Price"
            value={formatPrice(town.price)}
            tone="neutral"
          />
          <MetricPill
            icon={GraduationCap}
            label="School"
            value={formatScore(town.schoolScore)}
            tone="primary"
          />
          <MetricPill
            icon={Shield}
            label="Safety"
            value={formatScore(town.safetyScore)}
            tone="accent"
          />
          <MetricPill
            icon={Car}
            label={town.commuteDestinationLabel ? `To ${town.commuteDestinationLabel.replace('Boston / South Station', 'Boston')}` : 'Commute'}
            value={formatCommute(town.commuteMinutes)}
            tone="neutral"
          />
        </div>

        {matchReason && (
          <p className="text-xs leading-relaxed text-muted-foreground">
            <span className="font-medium text-foreground">Why it matched: </span>
            {matchReason}
          </p>
        )}
      </CardContent>
    </Card>
  )
}

function MetricPill({
  icon: Icon,
  label,
  value,
  tone,
}: {
  icon: typeof DollarSign
  label: string
  value: string
  tone: 'primary' | 'accent' | 'neutral'
}) {
  return (
    <div
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs',
        tone === 'primary' && 'border-primary/15 bg-primary/5 text-primary',
        tone === 'accent' && 'border-accent/20 bg-accent/5 text-accent',
        tone === 'neutral' && 'border-border bg-muted/40 text-foreground',
      )}
    >
      <Icon className="size-3 opacity-70" aria-hidden />
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  )
}
