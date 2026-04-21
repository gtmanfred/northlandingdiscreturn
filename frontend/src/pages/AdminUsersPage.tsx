import { useQueryClient } from '@tanstack/react-query'
import {
  useAdminListUsers,
  useAdminUpdateUser,
  getAdminListUsersQueryKey,
} from '../api/northlanding'
import { LoadingSpinner } from '../components/LoadingSpinner'

export function AdminUsersPage() {
  const queryClient = useQueryClient()
  const { data: users, isLoading } = useAdminListUsers()
  const updateMutation = useAdminUpdateUser()

  const handlePromote = async (userId: string, name: string, currentAdmin: boolean) => {
    const action = currentAdmin ? 'Remove admin from' : 'Promote'
    if (!confirm(`${action} ${name}?`)) return
    await updateMutation.mutateAsync({ userId, data: { is_admin: !currentAdmin } })
    queryClient.invalidateQueries({ queryKey: getAdminListUsersQueryKey() })
  }

  if (isLoading) return <LoadingSpinner />

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6 text-green-800">Users</h1>

      <div className="overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="bg-gray-100 text-left">
              <th className="px-3 py-2 border border-gray-200">Name</th>
              <th className="px-3 py-2 border border-gray-200">Email</th>
              <th className="px-3 py-2 border border-gray-200">Phones</th>
              <th className="px-3 py-2 border border-gray-200">Admin</th>
              <th className="px-3 py-2 border border-gray-200">Actions</th>
            </tr>
          </thead>
          <tbody>
            {(users ?? []).map((user) => (
              <tr key={user.id} className="border-b border-gray-100 hover:bg-gray-50">
                <td className="px-3 py-2 border border-gray-200 font-medium">{user.name}</td>
                <td className="px-3 py-2 border border-gray-200 text-gray-600">{user.email}</td>
                <td className="px-3 py-2 border border-gray-200">
                  {user.phone_numbers
                    ?.filter((p) => p.verified)
                    .map((p) => p.number)
                    .join(', ') || '—'}
                </td>
                <td className="px-3 py-2 border border-gray-200">
                  {user.is_admin ? (
                    <span className="px-2 py-0.5 bg-blue-100 text-blue-700 rounded text-xs">Admin</span>
                  ) : '—'}
                </td>
                <td className="px-3 py-2 border border-gray-200">
                  <button
                    onClick={() => handlePromote(user.id, user.name, user.is_admin)}
                    disabled={updateMutation.isPending}
                    className={`text-sm ${user.is_admin ? 'text-red-500 hover:text-red-700' : 'text-blue-600 hover:text-blue-800'} disabled:opacity-50`}
                  >
                    {user.is_admin ? 'Remove admin' : 'Make admin'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
