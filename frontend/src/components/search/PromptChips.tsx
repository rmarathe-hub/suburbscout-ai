import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { EXAMPLE_PROMPTS, type ExamplePrompt } from '@/lib/prompts'
import { cn } from '@/lib/utils'

interface PromptChipsProps {
  onSelect: (prompt: string) => void
  disabled?: boolean
  prompts?: ExamplePrompt[]
}

export function PromptChips({
  onSelect,
  disabled = false,
  prompts = EXAMPLE_PROMPTS,
}: PromptChipsProps) {
  return (
    <div className="flex flex-wrap justify-center gap-2 lg:justify-start">
      {prompts.map((item) => (
        <Button
          key={item.label}
          type="button"
          variant="outline"
          size="sm"
          disabled={disabled}
          onClick={() => onSelect(item.prompt)}
          className={cn(
            'h-auto max-w-full whitespace-normal rounded-full px-3 py-1.5 text-left text-xs sm:text-sm',
            item.variant === 'demo' && 'border-amber-300/80 bg-amber-50/80 hover:bg-amber-100/80',
          )}
        >
          {item.variant === 'demo' && (
            <Badge
              variant="outline"
              className="mr-1.5 border-amber-400/60 bg-amber-100/50 px-1 py-0 text-[0.65rem] text-amber-900"
            >
              demo
            </Badge>
          )}
          {item.label}
        </Button>
      ))}
    </div>
  )
}
