import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

type DiscStatus = 'returned' | 'final_notice' | 'waiting'

const styles: Record<DiscStatus, string> = {
  returned: 'border-transparent bg-green-100 text-green-800 hover:bg-green-100',
  final_notice: 'border-transparent bg-red-100 text-red-800 hover:bg-red-100',
  waiting: 'border-transparent bg-yellow-100 text-yellow-800 hover:bg-yellow-100',
}

const labels: Record<DiscStatus, string> = {
  returned: 'Returned',
  final_notice: 'Final notice sent',
  waiting: 'Waiting for pickup',
}

interface StatusBadgeProps {
  status: DiscStatus
  className?: string
}

export function StatusBadge({ status, className }: StatusBadgeProps) {
  return (
    <Badge variant="outline" className={cn(styles[status], className)}>
      {labels[status]}
    </Badge>
  )
}

export function discStatus({
  is_returned,
  final_notice_sent,
}: {
  is_returned?: boolean | null
  final_notice_sent?: boolean | null
}): DiscStatus {
  if (is_returned) return 'returned'
  if (final_notice_sent) return 'final_notice'
  return 'waiting'
}
