import { Badge } from '@/components/ui/badge'
import { useHealth } from '@/hooks/useHealth'
import { backendModeLabel } from '@/lib/format'

export function BackendStatus() {
  const health = useHealth()

  if (health.status === 'loading') {
    return (
      <Badge variant="secondary" className="shrink-0">
        {health.message}
      </Badge>
    )
  }

  if (health.status === 'error') {
    return (
      <Badge variant="destructive" className="shrink-0">
        API offline
      </Badge>
    )
  }

  const { data } = health
  const dbOk = data.database === 'ok'
  const datasetOk = data.suburbs_dataset_loaded

  return (
    <div className="flex flex-wrap items-center justify-end gap-2">
      <Badge variant="secondary" className="shrink-0">
        Backend: {backendModeLabel(data.backend_agent_mode)}
      </Badge>
      {!datasetOk && (
        <Badge variant="outline" className="shrink-0 text-amber-700">
          Dataset missing
        </Badge>
      )}
      {!dbOk && (
        <Badge variant="outline" className="shrink-0 text-muted-foreground">
          DB {data.database}
        </Badge>
      )}
    </div>
  )
}
