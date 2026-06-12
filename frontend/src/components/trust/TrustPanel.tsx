import { Shield } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'

const TRUST_POINTS = [
  'Answers use a curated dataset of 200 Boston-area towns.',
  'Scores are 0–10 percentile ranks within that dataset — not official government ratings.',
  'Commute times are measured to South Station, Boston.',
  'We do not use live Zillow, Redfin, or MLS listing feeds.',
] as const

export function TrustPanel() {
  return (
    <Card className="shadow-[var(--shadow-card)]">
      <CardHeader className="pb-2">
        <div className="flex items-center gap-2">
          <Shield className="size-4 text-primary" aria-hidden />
          <CardTitle className="text-base">Grounded AI</CardTitle>
        </div>
        <CardDescription>How SuburbScout answers</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm text-muted-foreground">
        <ul className="space-y-2">
          {TRUST_POINTS.map((point) => (
            <li key={point} className="leading-relaxed">
              {point}
            </li>
          ))}
        </ul>
        <div className="flex flex-wrap gap-2 pt-1">
          <Badge variant="secondary">200 towns</Badge>
          <Badge variant="secondary">Percentile scores</Badge>
          <Badge variant="secondary">No live MLS</Badge>
        </div>
      </CardContent>
    </Card>
  )
}
