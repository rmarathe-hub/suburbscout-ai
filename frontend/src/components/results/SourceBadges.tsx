import { Cloud, Database, Gauge, Server } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import type { QueryResponse } from '@/api/types'
import { sourceLabel } from '@/lib/format'
import { cn } from '@/lib/utils'

interface SourceBadgesProps {
  response: QueryResponse
  className?: string
}

export function SourceBadges({ response, className }: SourceBadgesProps) {
  const isFoundry = response.source === 'foundry_hosted_agent'
  const agentVersion = response.metadata?.agent_version
  const agentName = response.metadata?.agent_name

  const commuteDestination =
    typeof response.metadata?.commute_destination === 'string'
      ? response.metadata.commute_destination
      : null
  const commuteIsDefault = response.metadata?.commute_destination_is_default !== false

  return (
    <div className={cn('flex flex-wrap gap-2', className)}>
      <Badge
        variant="secondary"
        className={cn(
          'gap-1 font-normal',
          isFoundry
            ? 'border-primary/20 bg-primary/10 text-primary'
            : 'border-accent/20 bg-accent/10 text-accent',
        )}
      >
        {isFoundry ? (
          <Cloud className="size-3" aria-hidden />
        ) : (
          <Server className="size-3" aria-hidden />
        )}
        Source: {sourceLabel(response.source)}
      </Badge>

      {isFoundry && agentName && (
        <Badge variant="outline" className="gap-1 font-normal text-muted-foreground">
          {agentName}
          {agentVersion ? ` v${agentVersion}` : ''}
        </Badge>
      )}

      <Badge variant="outline" className="gap-1 font-normal text-muted-foreground">
        <Database className="size-3" aria-hidden />
        Dataset: 200 towns
      </Badge>

      <Badge variant="outline" className="gap-1 font-normal text-muted-foreground">
        <Gauge className="size-3" aria-hidden />
        Scores: percentile-based
      </Badge>

      {commuteDestination && !commuteIsDefault && (
        <Badge variant="outline" className="gap-1 font-normal text-primary">
          Destination: {commuteDestination}
        </Badge>
      )}

      {response.execution_status && response.execution_status !== 'ok' && (
        <Badge
          variant="outline"
          className={cn(
            'font-normal',
            response.execution_status === 'error' && 'border-destructive/40 text-destructive',
            response.execution_status === 'out_of_scope' && 'border-amber-400/50 text-amber-800',
          )}
        >
          Status: {response.execution_status}
        </Badge>
      )}
    </div>
  )
}
