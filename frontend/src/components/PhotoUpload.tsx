import { useCallback, useState } from 'react'
import { useDropzone } from 'react-dropzone'
import { useQueryClient } from '@tanstack/react-query'
import { useUploadDiscPhoto, useDeleteDiscPhoto, getListDiscsQueryKey } from '../api/northlanding'

interface PhotoUploadProps {
  discId: string
  existingPhotos: Array<{ id: string; photo_path: string; sort_order: number }>
}

export function PhotoUpload({ discId, existingPhotos }: PhotoUploadProps) {
  const queryClient = useQueryClient()
  const uploadMutation = useUploadDiscPhoto()
  const deleteMutation = useDeleteDiscPhoto()
  const [uploading, setUploading] = useState(false)

  const onDrop = useCallback(
    async (acceptedFiles: File[]) => {
      setUploading(true)
      for (const file of acceptedFiles) {
        await uploadMutation.mutateAsync({ discId, data: { file } })
      }
      queryClient.invalidateQueries({ queryKey: getListDiscsQueryKey() })
      setUploading(false)
    },
    [discId, queryClient, uploadMutation],
  )

  const { getRootProps, getInputProps, isDragActive, open } = useDropzone({
    onDrop,
    accept: { 'image/*': ['.jpg', '.jpeg', '.png', '.webp'] },
    multiple: true,
  })

  const handleDelete = async (photoId: string) => {
    await deleteMutation.mutateAsync({ discId, photoId })
    queryClient.invalidateQueries({ queryKey: getListDiscsQueryKey() })
  }

  return (
    <div>
      {/* Thumbnails */}
      <div className="flex gap-2 mb-3 flex-wrap">
        {existingPhotos.map((photo) => (
          <div key={photo.id} className="relative group w-20 h-20">
            <img src={photo.photo_path} alt="" className="w-20 h-20 object-cover rounded" />
            <button
              onClick={() => handleDelete(photo.id)}
              className="absolute top-0 right-0 bg-red-500 text-white rounded-full w-5 h-5 text-xs opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center"
            >
              ×
            </button>
          </div>
        ))}
      </div>

      {/* Shared hidden file input */}
      <input {...getInputProps()} />

      {/* Mobile: tap button */}
      <button
        type="button"
        onClick={open}
        disabled={uploading}
        className="md:hidden w-full py-4 border-2 border-dashed border-gray-300 rounded-lg text-gray-500 text-sm disabled:opacity-50"
      >
        {uploading ? 'Uploading…' : '+ Add Photos'}
      </button>

      {/* Desktop: drag zone */}
      <div
        {...getRootProps()}
        className={`hidden md:block border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors ${
          isDragActive ? 'border-green-500 bg-green-50' : 'border-gray-300 hover:border-gray-400'
        }`}
      >
        {uploading ? (
          <p className="text-gray-500">Uploading…</p>
        ) : isDragActive ? (
          <p className="text-green-600">Drop photos here</p>
        ) : (
          <p className="text-gray-500">Drag & drop photos here, or click to select</p>
        )}
      </div>
    </div>
  )
}
