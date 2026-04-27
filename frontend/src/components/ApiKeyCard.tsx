import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { format } from 'date-fns'
import {
  useGetApiKeyUsersMeApiKeyGet,
  useCreateApiKeyUsersMeApiKeyPost,
  useDeleteApiKeyUsersMeApiKeyDelete,
  getGetApiKeyUsersMeApiKeyGetQueryKey,
  type ApiKeyCreated,
} from '../api/northlanding'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Alert, AlertDescription } from '@/components/ui/alert'

function is404(err: unknown): boolean {
  return (err as { response?: { status?: number } })?.response?.status === 404
}

export function ApiKeyCard() {
  const queryClient = useQueryClient()
  const [newKey, setNewKey] = useState<ApiKeyCreated | null>(null)
  const [error, setError] = useState('')

  const { data: keyMeta, error: getError } = useGetApiKeyUsersMeApiKeyGet({
    query: { retry: false },
  })

  const createKey = useCreateApiKeyUsersMeApiKeyPost()
  const deleteKey = useDeleteApiKeyUsersMeApiKeyDelete()

  const hasKey = keyMeta !== undefined && !is404(getError)
  const noKey = is404(getError) && !keyMeta

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: getGetApiKeyUsersMeApiKeyGetQueryKey() })

  const handleGenerate = async () => {
    setError('')
    try {
      const result = await createKey.mutateAsync()
      setNewKey(result)
      await invalidate()
    } catch {
      setError('Failed to generate API key.')
    }
  }

  const handleRegenerate = async () => {
    if (!window.confirm('This will invalidate your existing API key. Continue?')) return
    setError('')
    try {
      const result = await createKey.mutateAsync()
      setNewKey(result)
      await invalidate()
    } catch {
      setError('Failed to regenerate API key.')
    }
  }

  const handleRevoke = async () => {
    if (!window.confirm('Revoke your API key? Existing scripts will stop working.')) return
    setError('')
    try {
      await deleteKey.mutateAsync()
      await invalidate()
    } catch {
      setError('Failed to revoke API key.')
    }
  }

  const handleCopy = async () => {
    if (!newKey) return
    await navigator.clipboard.writeText(newKey.api_key)
    toast.success('Copied to clipboard')
  }

  const handleDismiss = () => setNewKey(null)

  const formatDate = (iso: string | null | undefined) =>
    iso ? format(new Date(iso), 'MMM d, yyyy') : 'never'

  return (
    <Card className="mt-6">
      <CardHeader>
        <CardTitle className="text-base">API Key</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {newKey && (
          <Alert>
            <AlertDescription className="space-y-3">
              <p className="text-sm font-medium">
                This key will not be shown again — copy it now.
              </p>
              <div className="flex items-center gap-2">
                <code className="flex-1 break-all rounded bg-muted px-2 py-1 font-mono text-sm">
                  {newKey.api_key}
                </code>
                <Button variant="outline" size="sm" onClick={handleCopy}>
                  Copy
                </Button>
              </div>
              <Button variant="secondary" size="sm" onClick={handleDismiss}>
                Dismiss
              </Button>
            </AlertDescription>
          </Alert>
        )}

        {!newKey && noKey && (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">
              Generate a personal API key to call the API without OAuth.
            </p>
            <Button onClick={handleGenerate} disabled={createKey.isPending}>
              Generate API Key
            </Button>
          </div>
        )}

        {!newKey && hasKey && keyMeta && (
          <div className="space-y-3">
            <div className="rounded-md border border-border px-3 py-2">
              <p className="font-mono text-sm">
                <span className="text-muted-foreground">••••</span>{' '}
                <span>{keyMeta.last_four}</span>
              </p>
              <p className="text-xs text-muted-foreground">
                Created: {formatDate(keyMeta.created_at)}
              </p>
              <p className="text-xs text-muted-foreground">
                Last used: {formatDate(keyMeta.last_used_at ?? null)}
              </p>
            </div>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={handleRegenerate}
                disabled={createKey.isPending}
              >
                Regenerate
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="text-destructive hover:text-destructive"
                onClick={handleRevoke}
                disabled={deleteKey.isPending}
              >
                Revoke
              </Button>
            </div>
          </div>
        )}

        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
      </CardContent>
    </Card>
  )
}
