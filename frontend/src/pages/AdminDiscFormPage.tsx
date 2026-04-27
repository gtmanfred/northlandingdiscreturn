import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { ImagePlus, X } from 'lucide-react'
import {
  useCreateDisc,
  useUpdateDisc,
  useUploadDiscPhoto,
  useListDiscs,
  useGetSuggestions,
  useGetPhoneSuggestions,
  getListDiscsQueryKey,
  getGetSuggestionsQueryKey,
} from '../api/northlanding'
import { AutocompleteInput, type Suggestion } from '../components/AutocompleteInput'
import { PhotoUpload } from '../components/PhotoUpload'
import { PageHeader } from '../components/PageHeader'
import { LoadingState } from '../components/LoadingState'
import { PhoneInput } from '../components/PhoneInput'
import { normalizePhone } from '../utils/phone'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Alert, AlertDescription } from '@/components/ui/alert'

interface DiscFormState {
  manufacturer: string
  name: string
  color: string
  input_date: string
  owner_first_name: string
  owner_last_name: string
  phone_number: string
  notes: string
  is_clear: boolean
  is_found: boolean
  is_returned: boolean
}

const defaultForm: DiscFormState = {
  manufacturer: '',
  name: '',
  color: '',
  input_date: new Date().toISOString().slice(0, 10),
  owner_first_name: '',
  owner_last_name: '',
  phone_number: '',
  notes: '',
  is_clear: false,
  is_found: true,
  is_returned: false,
}

const inputCls =
  'flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50'

export function AdminDiscFormPage() {
  const { discId } = useParams<{ discId?: string }>()
  const isEdit = !!discId
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const { data: listData, isLoading } = useListDiscs(
    { page: 1, page_size: 1000 },
    { query: { enabled: isEdit } },
  )
  const existingDisc = listData?.items.find((d) => d.id === discId)

  const [form, setForm] = useState<DiscFormState>(defaultForm)
  const [stagedPhotos, setStagedPhotos] = useState<File[]>([])
  const [error, setError] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)

  const stagedPreviews = useMemo(
    () => stagedPhotos.map((f) => URL.createObjectURL(f)),
    [stagedPhotos],
  )

  useEffect(() => {
    return () => stagedPreviews.forEach((url) => URL.revokeObjectURL(url))
  }, [stagedPreviews])

  const { data: manufacturerSuggestions = [] } = useGetSuggestions({ field: 'manufacturer' })
  const { data: nameSuggestions = [] } = useGetSuggestions({ field: 'name' })
  const { data: colorSuggestions = [] } = useGetSuggestions({ field: 'color' })
  const { data: ownerFirstNameSuggestions = [] } = useGetSuggestions(
    { field: 'owner_first_name' },
    { query: { retry: false } },
  )
  const { data: ownerLastNameSuggestions = [] } = useGetSuggestions(
    { field: 'owner_last_name' },
    { query: { retry: false } },
  )
  const { data: rawPhoneSuggestions = [] } = useGetPhoneSuggestions(
    {
      owner_first_name: form.owner_first_name,
      owner_last_name: form.owner_last_name,
    },
    { query: { enabled: !!form.owner_first_name || !!form.owner_last_name } },
  )
  const phoneSuggestions: Suggestion[] = rawPhoneSuggestions.map((s) => ({
    value: s.number,
    label: s.label,
  }))

  useEffect(() => {
    if (existingDisc) {
      setForm({
        manufacturer: existingDisc.manufacturer,
        name: existingDisc.name,
        color: existingDisc.color,
        input_date: existingDisc.input_date,
        owner_first_name: existingDisc.owner?.first_name ?? '',
        owner_last_name: existingDisc.owner?.last_name ?? '',
        phone_number: existingDisc.owner?.phone_number ?? '',
        notes: existingDisc.notes ?? '',
        is_clear: existingDisc.is_clear,
        is_found: existingDisc.is_found,
        is_returned: existingDisc.is_returned,
      })
    }
  }, [existingDisc])

  const createMutation = useCreateDisc()
  const updateMutation = useUpdateDisc()
  const uploadMutation = useUploadDiscPhoto()

  const set = (field: keyof DiscFormState) =>
    (e: React.ChangeEvent<HTMLInputElement>) =>
      setForm((f) => ({
        ...f,
        [field]: e.target.type === 'checkbox' ? e.target.checked : e.target.value,
      }))

  const setValue = (field: keyof DiscFormState) => (value: string) =>
    setForm((f) => ({ ...f, [field]: value }))

  const handleOwnerFirstNameChange = (value: string) =>
    setForm((f) => ({ ...f, owner_first_name: value, phone_number: '' }))
  const handleOwnerLastNameChange = (value: string) =>
    setForm((f) => ({ ...f, owner_last_name: value, phone_number: '' }))

  const handlePhotoSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? [])
    setStagedPhotos((prev) => [...prev, ...files])
    e.target.value = ''
  }

  const submitForm = async (andAddAnother: boolean) => {
    setError('')
    let normalizedPhone: string | null = null
    if (form.phone_number) {
      try {
        normalizedPhone = normalizePhone(form.phone_number)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Invalid phone number.')
        return
      }
    }
    const ownerSet =
      !!form.owner_first_name || !!form.owner_last_name || !!normalizedPhone
    const payload = {
      manufacturer: form.manufacturer,
      name: form.name,
      color: form.color,
      input_date: form.input_date,
      is_clear: form.is_clear,
      is_found: form.is_found,
      is_returned: form.is_returned,
      notes: form.notes || null,
      owner_first_name: ownerSet ? form.owner_first_name : null,
      owner_last_name: ownerSet ? form.owner_last_name : null,
      phone_number: ownerSet ? normalizedPhone : null,
    }
    try {
      if (isEdit) {
        await updateMutation.mutateAsync({ discId, data: payload })
        queryClient.invalidateQueries({ queryKey: getListDiscsQueryKey() })
        queryClient.invalidateQueries({ queryKey: getGetSuggestionsQueryKey() })
        navigate('/admin/discs')
      } else {
        const created = await createMutation.mutateAsync({ data: payload })
        let photoError = false
        for (const file of stagedPhotos) {
          try {
            await uploadMutation.mutateAsync({ discId: created.id, data: { file } })
          } catch {
            photoError = true
          }
        }
        queryClient.invalidateQueries({ queryKey: getListDiscsQueryKey() })
        queryClient.invalidateQueries({ queryKey: getGetSuggestionsQueryKey() })
        if (andAddAnother) {
          setForm({ ...defaultForm, input_date: new Date().toISOString().slice(0, 10) })
          setStagedPhotos([])
        } else {
          navigate('/admin/discs')
        }
        if (photoError) {
          setError('Disc saved, but one or more photos failed to upload.')
        }
      }
    } catch {
      setError(isEdit ? 'Failed to update disc.' : 'Failed to create disc.')
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    await submitForm(false)
  }

  if (isEdit && isLoading) return <LoadingState />
  if (isEdit && !isLoading && !existingDisc)
    return (
      <Alert variant="destructive">
        <AlertDescription>Disc not found.</AlertDescription>
      </Alert>
    )

  const isSaving =
    createMutation.isPending || updateMutation.isPending || uploadMutation.isPending

  return (
    <div className="max-w-xl">
      <PageHeader title={isEdit ? 'Edit Disc' : 'Add Disc'} />

      <form onSubmit={handleSubmit} className="space-y-4">
        <Card>
          <CardContent className="space-y-4 pt-6">
            {(
              [
                { field: 'manufacturer', suggestions: manufacturerSuggestions, label: 'Manufacturer' },
                { field: 'name', suggestions: nameSuggestions, label: 'Name' },
                { field: 'color', suggestions: colorSuggestions, label: 'Color' },
              ] as const
            ).map(({ field, suggestions, label }) => (
              <div key={field} className="space-y-1.5">
                <Label htmlFor={`disc-${field}`}>{label} *</Label>
                <AutocompleteInput
                  id={`disc-${field}`}
                  required
                  value={form[field]}
                  suggestions={suggestions.map((v) => ({ value: v }))}
                  onValueChange={setValue(field)}
                  className={inputCls}
                />
              </div>
            ))}

            <div className="space-y-1.5">
              <Label htmlFor="disc-input-date">Input date *</Label>
              <Input
                id="disc-input-date"
                type="date"
                required
                value={form.input_date}
                onChange={set('input_date')}
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="disc-owner-first">First name</Label>
                <AutocompleteInput
                  id="disc-owner-first"
                  value={form.owner_first_name}
                  suggestions={ownerFirstNameSuggestions.map((v) => ({ value: v }))}
                  onValueChange={handleOwnerFirstNameChange}
                  className={inputCls}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="disc-owner-last">Last name</Label>
                <AutocompleteInput
                  id="disc-owner-last"
                  value={form.owner_last_name}
                  suggestions={ownerLastNameSuggestions.map((v) => ({ value: v }))}
                  onValueChange={handleOwnerLastNameChange}
                  className={inputCls}
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="disc-phone">Phone number</Label>
              <PhoneInput value={form.phone_number} onChange={setValue('phone_number')} />
              {phoneSuggestions.length > 0 && (
                <ul className="mt-2 space-y-1 rounded-md border border-input p-1">
                  {phoneSuggestions.map((s) => {
                    const selected =
                      form.phone_number.replace(/\D/g, '') ===
                      s.value.replace(/\D/g, '')
                    return (
                      <li key={s.value}>
                        <button
                          type="button"
                          onClick={() => setValue('phone_number')(s.value)}
                          className={`w-full rounded px-2 py-1 text-left text-sm transition-colors ${
                            selected
                              ? 'bg-primary text-primary-foreground'
                              : 'hover:bg-accent'
                          }`}
                        >
                          {s.label}
                        </button>
                      </li>
                    )
                  })}
                </ul>
              )}
            </div>

            <div className="flex flex-wrap gap-6 pt-1">
              {(['is_clear', 'is_found', 'is_returned'] as const).map((field) => (
                <label key={field} className="flex cursor-pointer items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={form[field]}
                    onChange={set(field)}
                    className="h-4 w-4 rounded border-input accent-primary"
                  />
                  {field.replace('is_', '').replace('_', ' ')}
                </label>
              ))}
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="disc-notes">Notes</Label>
              <textarea
                id="disc-notes"
                rows={3}
                value={form.notes}
                onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
                className={`${inputCls} h-auto py-2`}
              />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="space-y-3 pt-6">
            <Label>Photos</Label>
            {isEdit && existingDisc ? (
              <PhotoUpload discId={discId!} existingPhotos={existingDisc.photos ?? []} />
            ) : (
              <>
                {stagedPhotos.length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    {stagedPhotos.map((_file, i) => (
                      <div key={i} className="group relative h-20 w-20">
                        <img
                          src={stagedPreviews[i]}
                          alt=""
                          className="h-20 w-20 rounded-md object-cover"
                        />
                        <button
                          type="button"
                          onClick={() =>
                            setStagedPhotos((p) => p.filter((_, j) => j !== i))
                          }
                          className="absolute -right-1 -top-1 flex h-5 w-5 items-center justify-center rounded-full bg-destructive text-destructive-foreground opacity-0 transition-opacity group-hover:opacity-100"
                          aria-label="Remove photo"
                        >
                          <X className="h-3 w-3" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*"
                  multiple
                  className="hidden"
                  onChange={handlePhotoSelect}
                />
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="flex w-full items-center justify-center gap-2 rounded-lg border-2 border-dashed border-border py-4 text-sm text-muted-foreground hover:border-muted-foreground/60"
                >
                  <ImagePlus className="h-4 w-4" />
                  Add photos
                </button>
              </>
            )}
          </CardContent>
        </Card>

        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        <div className="sticky bottom-0 -mx-4 flex flex-col gap-2 border-t bg-background/95 px-4 py-3 backdrop-blur sm:relative sm:mx-0 sm:flex-row sm:border-0 sm:bg-transparent sm:p-0">
          <Button type="submit" disabled={isSaving}>
            {isSaving ? 'Saving…' : isEdit ? 'Update' : 'Create'}
          </Button>
          {!isEdit && (
            <Button
              type="button"
              variant="secondary"
              disabled={isSaving}
              onClick={() => submitForm(true)}
            >
              Save and Add Another
            </Button>
          )}
          <Button type="button" variant="outline" onClick={() => navigate('/admin/discs')}>
            Cancel
          </Button>
        </div>
      </form>
    </div>
  )
}
