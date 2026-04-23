import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { Trash2 } from 'lucide-react'
import {
  useGetMyWishlist,
  useAddWishlistDisc,
  useRemoveWishlistDisc,
  useGetSuggestions,
  useGetMe,
  getGetMyWishlistQueryKey,
} from '../api/northlanding'
import { AutocompleteInput } from '../components/AutocompleteInput'
import { PageHeader } from '../components/PageHeader'
import { EmptyState } from '../components/EmptyState'
import { LoadingState } from '../components/LoadingState'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

export function MyWishlistPage() {
  const queryClient = useQueryClient()
  const { data: user, isLoading: userLoading } = useGetMe()
  const { data: discs, isLoading: discsLoading } = useGetMyWishlist()
  const addMutation = useAddWishlistDisc()
  const removeMutation = useRemoveWishlistDisc()
  const { data: manufacturerSuggestions = [] } = useGetSuggestions({ field: 'manufacturer' })
  const { data: nameSuggestions = [] } = useGetSuggestions({ field: 'name' })
  const { data: colorSuggestions = [] } = useGetSuggestions({ field: 'color' })

  const verifiedNumbers = user?.phone_numbers?.filter((p) => p.verified) ?? []

  const [form, setForm] = useState({ manufacturer: '', name: '', color: '' })
  const [selectedPhone, setSelectedPhone] = useState<string>('')

  const phoneNumber = selectedPhone || verifiedNumbers[0]?.number || ''

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault()
    await addMutation.mutateAsync({
      data: {
        ...form,
        phone_number: phoneNumber,
        owner_name: user?.name ?? undefined,
      },
    })
    queryClient.invalidateQueries({ queryKey: getGetMyWishlistQueryKey() })
    setForm({ manufacturer: '', name: '', color: '' })
  }

  const handleRemove = async (discId: string) => {
    await removeMutation.mutateAsync({ discId })
    queryClient.invalidateQueries({ queryKey: getGetMyWishlistQueryKey() })
  }

  if (userLoading || discsLoading) return <LoadingState />

  const inputCls =
    'w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2'

  return (
    <div>
      <PageHeader
        title="My Wishlist"
        description="Log discs you lost at North Landing so staff can match them if found."
      />

      {verifiedNumbers.length === 0 ? (
        <Alert className="mb-8 border-yellow-200 bg-yellow-50 text-yellow-900">
          <AlertDescription>
            Add and verify a phone number in your account settings before adding discs to your wishlist.
          </AlertDescription>
        </Alert>
      ) : (
        <Card className="mb-8">
          <CardContent className="pt-6">
            <form onSubmit={handleAdd} className="flex flex-wrap gap-3">
              <AutocompleteInput
                containerClassName="flex-1 min-w-32"
                className={inputCls}
                placeholder="Manufacturer"
                value={form.manufacturer}
                suggestions={manufacturerSuggestions.map((v) => ({ value: v }))}
                onValueChange={(v) => setForm((f) => ({ ...f, manufacturer: v }))}
              />
              <AutocompleteInput
                containerClassName="flex-1 min-w-32"
                className={inputCls}
                placeholder="Disc name"
                value={form.name}
                suggestions={nameSuggestions.map((v) => ({ value: v }))}
                onValueChange={(v) => setForm((f) => ({ ...f, name: v }))}
              />
              <AutocompleteInput
                containerClassName="flex-1 min-w-24"
                className={inputCls}
                placeholder="Color"
                value={form.color}
                suggestions={colorSuggestions.map((v) => ({ value: v }))}
                onValueChange={(v) => setForm((f) => ({ ...f, color: v }))}
              />
              {verifiedNumbers.length > 1 ? (
                <Select value={phoneNumber} onValueChange={setSelectedPhone}>
                  <SelectTrigger className="w-44" aria-label="Phone number">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {verifiedNumbers.map((p) => (
                      <SelectItem key={p.id} value={p.number}>
                        {p.number}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : (
                <span className="flex items-center rounded-md border border-border bg-muted px-3 text-sm text-muted-foreground">
                  {verifiedNumbers[0].number}
                </span>
              )}
              <Button type="submit" disabled={addMutation.isPending}>
                Add
              </Button>
            </form>
          </CardContent>
        </Card>
      )}

      {!discs?.length ? (
        <EmptyState title="Your wishlist is empty" description="Add discs above to start matching." />
      ) : (
        <ul className="space-y-2">
          {discs.map((disc) => (
            <li key={disc.id}>
              <Card>
                <CardContent className="flex items-center justify-between p-3">
                  <span>
                    <span className="font-medium text-foreground">{disc.name}</span>
                    {disc.manufacturer && (
                      <span className="ml-2 text-sm text-muted-foreground">{disc.manufacturer}</span>
                    )}
                    {disc.color && (
                      <span className="ml-2 text-sm text-muted-foreground">· {disc.color}</span>
                    )}
                  </span>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleRemove(disc.id)}
                    disabled={removeMutation.isPending}
                    className="text-destructive hover:text-destructive"
                  >
                    <Trash2 className="mr-1 h-4 w-4" />
                    Remove
                  </Button>
                </CardContent>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
