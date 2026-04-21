import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import {
  useCreateDisc,
  useUpdateDisc,
  useListDiscs,
  getListDiscsQueryKey,
} from '../api/northlanding'
import { PhotoUpload } from '../components/PhotoUpload'
import { LoadingSpinner } from '../components/LoadingSpinner'

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
  const [error, setError] = useState('')

  const set = (field: keyof DiscFormState) =>
    (e: React.ChangeEvent<HTMLInputElement>) =>
      setForm((f) => ({ ...f, [field]: e.target.type === 'checkbox' ? e.target.checked : e.target.value }))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    const payload = {
      ...form,
      owner_name: form.owner_name || null,
      phone_number: form.phone_number || null,
    }
    try {
      if (isEdit) {
        await updateMutation.mutateAsync({ discId, data: payload })
      } else {
        await createMutation.mutateAsync({ data: payload })
      }
      queryClient.invalidateQueries({ queryKey: getListDiscsQueryKey() })
      navigate('/admin/discs')
    } catch {
      setError(isEdit ? 'Failed to update disc.' : 'Failed to create disc.')
    }
  }

  if (isEdit && isLoading) return <LoadingSpinner />
  if (isEdit && !isLoading && !existingDisc) return (
    <div className="p-8 text-center text-red-600">Disc not found.</div>
  )

  const isSaving = createMutation.isPending || updateMutation.isPending

  return (
    <div className="max-w-lg">
      <h1 className="text-2xl font-bold mb-6 text-green-800">
        {isEdit ? 'Edit Disc' : 'Add Disc'}
      </h1>

      <form onSubmit={handleSubmit} className="space-y-4">
        {(['manufacturer', 'name', 'color'] as const).map((field) => (
          <div key={field}>
            <label className="block text-sm font-medium text-gray-700 mb-1 capitalize">{field} *</label>
            <input
              required
              value={form[field]}
              onChange={set(field)}
              className="w-full border border-gray-300 rounded px-3 py-2"
            />
          </div>
        ))}

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Input Date *</label>
          <input
            type="date"
            required
            value={form.input_date}
            onChange={set('input_date')}
            className="w-full border border-gray-300 rounded px-3 py-2"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Owner Name</label>
          <input value={form.owner_name} onChange={set('owner_name')} className="w-full border border-gray-300 rounded px-3 py-2" />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Phone Number (E.164)</label>
          <input
            type="tel"
            placeholder="+15551234567"
            value={form.phone_number}
            onChange={set('phone_number')}
            className="w-full border border-gray-300 rounded px-3 py-2"
          />
        </div>

        <div className="flex gap-6">
          {(['is_clear', 'is_found', 'is_returned'] as const).map((field) => (
            <label key={field} className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={form[field]} onChange={set(field)} className="rounded" />
              {field.replace('is_', '').replace('_', ' ')}
            </label>
          ))}
        </div>

        {isEdit && existingDisc && (
          <div>
            <p className="text-sm font-medium text-gray-700 mb-2">Photos</p>
            <PhotoUpload discId={discId!} existingPhotos={existingDisc.photos ?? []} />
          </div>
        )}

        {error && <p className="text-red-600 text-sm">{error}</p>}

        <div className="flex gap-3 pt-2">
          <button
            type="submit"
            disabled={isSaving}
            className="bg-green-700 text-white px-6 py-2 rounded hover:bg-green-800 disabled:opacity-50"
          >
            {isSaving ? 'Saving…' : isEdit ? 'Update' : 'Create'}
          </button>
          <button
            type="button"
            onClick={() => navigate('/admin/discs')}
            className="px-6 py-2 border border-gray-300 rounded hover:bg-gray-50"
          >
            Cancel
          </button>
        </div>
      </form>
    </div>
  )
}
