import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
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
import { LoadingSpinner } from '../components/LoadingSpinner'
import { PhoneInput } from '../components/PhoneInput'
import { normalizePhone } from '../utils/phone'

interface DiscFormState {
  manufacturer: string
  name: string
  color: string
  input_date: string
  owner_name: string
  phone_number: string
  is_clear: boolean
  is_found: boolean
  is_returned: boolean
}

const defaultForm: DiscFormState = {
  manufacturer: '',
  name: '',
  color: '',
  input_date: new Date().toISOString().slice(0, 10),
  owner_name: '',
  phone_number: '',
  is_clear: false,
  is_found: true,
  is_returned: false,
}

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
  const { data: ownerNameSuggestions = [] } = useGetSuggestions(
    { field: 'owner_name' },
    { query: { retry: false } },
  )
  const { data: rawPhoneSuggestions = [] } = useGetPhoneSuggestions(
    { owner_name: form.owner_name },
    { query: { enabled: !!form.owner_name } },
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
        owner_name: existingDisc.owner_name ?? '',
        phone_number: existingDisc.phone_number ?? '',
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
      setForm((f) => ({ ...f, [field]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }))

  const setValue = (field: keyof DiscFormState) => (value: string) =>
    setForm((f) => ({ ...f, [field]: value }))

  const handleOwnerNameChange = (value: string) =>
    setForm((f) => ({ ...f, owner_name: value, phone_number: '' }))

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
    const payload = {
      ...form,
      owner_name: form.owner_name || null,
      phone_number: normalizedPhone,
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

  if (isEdit && isLoading) return <LoadingSpinner />
  if (isEdit && !isLoading && !existingDisc) return (
    <div className="p-8 text-center text-red-600">Disc not found.</div>
  )

  const isSaving = createMutation.isPending || updateMutation.isPending || uploadMutation.isPending

  const inputClass = 'w-full border border-gray-300 rounded px-3 py-3 text-base'

  return (
    <div className="max-w-lg">
      <h1 className="text-2xl font-bold mb-6 text-green-800">
        {isEdit ? 'Edit Disc' : 'Add Disc'}
      </h1>

      <form onSubmit={handleSubmit} className="space-y-4">
        {(
          [
            { field: 'manufacturer', suggestions: manufacturerSuggestions },
            { field: 'name', suggestions: nameSuggestions },
            { field: 'color', suggestions: colorSuggestions },
          ] as const
        ).map(({ field, suggestions }) => (
          <div key={field}>
            <label className="block text-xs font-semibold uppercase tracking-wide text-gray-600 mb-1">
              {field} *
            </label>
            <AutocompleteInput
              required
              value={form[field]}
              suggestions={suggestions.map((v) => ({ value: v }))}
              onValueChange={setValue(field)}
              className={inputClass}
            />
          </div>
        ))}

        <div>
          <label className="block text-xs font-semibold uppercase tracking-wide text-gray-600 mb-1">
            Input Date *
          </label>
          <input
            type="date"
            required
            value={form.input_date}
            onChange={set('input_date')}
            className={inputClass}
          />
        </div>

        <div>
          <label className="block text-xs font-semibold uppercase tracking-wide text-gray-600 mb-1">
            Owner Name
          </label>
          <AutocompleteInput
            value={form.owner_name}
            suggestions={ownerNameSuggestions.map((v) => ({ value: v }))}
            onValueChange={handleOwnerNameChange}
            className={inputClass}
          />
        </div>

        <div>
          <label className="block text-xs font-semibold uppercase tracking-wide text-gray-600 mb-1">
            Phone Number
          </label>
          {phoneSuggestions.length > 0 ? (
            <AutocompleteInput
              type="tel"
              placeholder="(555) 123-4567"
              value={form.phone_number}
              suggestions={phoneSuggestions}
              onValueChange={setValue('phone_number')}
              className={inputClass}
            />
          ) : (
            <PhoneInput value={form.phone_number} onChange={setValue('phone_number')} className="py-3" />
          )}
        </div>

        <div className="flex gap-6 py-1">
          {(['is_clear', 'is_found', 'is_returned'] as const).map((field) => (
            <label key={field} className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={form[field]} onChange={set(field)} className="rounded w-5 h-5" />
              {field.replace('is_', '').replace('_', ' ')}
            </label>
          ))}
        </div>

        {/* Photos */}
        {isEdit && existingDisc ? (
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-gray-600 mb-2">Photos</p>
            <PhotoUpload discId={discId!} existingPhotos={existingDisc.photos ?? []} />
          </div>
        ) : (
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-gray-600 mb-2">Photos</p>
            {/* Staged photo thumbnails */}
            {stagedPhotos.length > 0 && (
              <div className="flex gap-2 mb-3 flex-wrap">
                {stagedPhotos.map((_file, i) => (
                  <div key={i} className="relative group w-20 h-20">
                    <img
                      src={stagedPreviews[i]}
                      alt=""
                      className="w-20 h-20 object-cover rounded"
                    />
                    <button
                      type="button"
                      onClick={() => setStagedPhotos((p) => p.filter((_, j) => j !== i))}
                      className="absolute top-0 right-0 bg-red-500 text-white rounded-full w-5 h-5 text-xs opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center"
                    >
                      ×
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
              className="w-full py-4 border-2 border-dashed border-gray-300 rounded-lg text-gray-500 text-sm hover:border-gray-400"
            >
              + Add Photos
            </button>
          </div>
        )}

        {error && <p className="text-red-600 text-sm">{error}</p>}

        <div className="flex flex-col sm:flex-row gap-3 pt-2">
          <button
            type="submit"
            disabled={isSaving}
            className="bg-green-700 text-white px-6 py-3 rounded hover:bg-green-800 disabled:opacity-50 text-base font-medium"
          >
            {isSaving ? 'Saving…' : isEdit ? 'Update' : 'Create'}
          </button>
          {!isEdit && (
            <button
              type="button"
              disabled={isSaving}
              onClick={() => submitForm(true)}
              className="bg-green-600 text-white px-6 py-3 rounded hover:bg-green-700 disabled:opacity-50 text-base font-medium"
            >
              Save and Add Another
            </button>
          )}
          <button
            type="button"
            onClick={() => navigate('/admin/discs')}
            className="px-6 py-3 border border-gray-300 rounded hover:bg-gray-50 text-base"
          >
            Cancel
          </button>
        </div>
      </form>
    </div>
  )
}
