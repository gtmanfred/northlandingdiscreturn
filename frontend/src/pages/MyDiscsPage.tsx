import { useGetMyDiscs } from '../api/northlanding'

export function MyDiscsPage() {
  const { data: discs, isLoading } = useGetMyDiscs()

  if (isLoading) return <div className="p-8 text-center text-gray-500">Loading…</div>

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6 text-green-800">My Discs</h1>
      {!discs?.length ? (
        <p className="text-gray-500">No discs found matching your linked phone numbers.</p>
      ) : (
        <div className="space-y-4">
          {discs.map((disc) => (
            <div key={disc.id} className="bg-white rounded-lg border border-gray-200 p-4 flex gap-4 items-start">
              {disc.photos?.[0] && (
                <img
                  src={disc.photos[0].photo_path}
                  alt={disc.name}
                  className="w-20 h-20 object-cover rounded"
                />
              )}
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-semibold">{disc.name}</span>
                  <span className="text-gray-500 text-sm">{disc.manufacturer}</span>
                  <span
                    className="inline-block w-4 h-4 rounded-full border border-gray-300"
                    style={{ backgroundColor: disc.color.toLowerCase() }}
                    title={disc.color}
                  />
                </div>
                {disc.owner_name && <p className="text-sm text-gray-600">Owner: {disc.owner_name}</p>}
                {disc.is_returned ? (
                  <span className="inline-block mt-1 px-2 py-0.5 bg-green-100 text-green-700 rounded text-xs">Returned</span>
                ) : disc.final_notice_sent ? (
                  <span className="inline-block mt-1 px-2 py-0.5 bg-red-100 text-red-700 rounded text-xs">Final notice sent</span>
                ) : (
                  <span className="inline-block mt-1 px-2 py-0.5 bg-yellow-100 text-yellow-700 rounded text-xs">Waiting for pickup</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
