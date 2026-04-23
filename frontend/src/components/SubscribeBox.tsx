import { useState } from 'react'
import { Copy, Check, CalendarDays } from 'lucide-react'
import { Button } from '@/components/ui/button'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export function SubscribeBox() {
  const url = `${API_URL}/pickup-events.ics`
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(url)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      window.open(url, '_blank')
    }
  }

  return (
    <div className="mb-6 flex flex-wrap items-center gap-3 rounded-md border bg-muted/40 p-3 text-sm">
      <CalendarDays className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
      <span className="text-muted-foreground">Calendar feed:</span>
      <code className="flex-1 overflow-x-auto text-xs">{url}</code>
      <Button size="sm" variant="outline" onClick={handleCopy}>
        {copied ? <Check className="mr-1 h-3 w-3" /> : <Copy className="mr-1 h-3 w-3" />}
        {copied ? 'Copied' : 'Copy'}
      </Button>
    </div>
  )
}
