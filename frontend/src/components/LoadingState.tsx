import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

interface LoadingStateProps {
  variant?: 'spinner' | 'list' | 'cards'
  rows?: number
  className?: string
}

export function LoadingState({ variant = 'spinner', rows = 4, className }: LoadingStateProps) {
  if (variant === 'spinner') {
    return (
      <div className={cn('flex items-center justify-center py-16 text-muted-foreground', className)}>
        <div
          role="status"
          className="h-8 w-8 animate-spin rounded-full border-2 border-muted border-t-primary"
        >
          <span className="sr-only">Loading…</span>
        </div>
      </div>
    )
  }

  if (variant === 'list') {
    return (
      <div className={cn('space-y-3', className)} role="status" aria-busy="true">
        <span className="sr-only">Loading…</span>
        {Array.from({ length: rows }).map((_, i) => (
          <Skeleton key={i} className="h-16 w-full" />
        ))}
      </div>
    )
  }

  return (
    <div
      className={cn('grid gap-4 sm:grid-cols-2 lg:grid-cols-3', className)}
      role="status"
      aria-busy="true"
    >
      <span className="sr-only">Loading…</span>
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-32 w-full" />
      ))}
    </div>
  )
}
