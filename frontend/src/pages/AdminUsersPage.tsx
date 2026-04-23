import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  useAdminListUsers,
  useAdminUpdateUser,
  getAdminListUsersQueryKey,
} from '../api/northlanding'
import { PageHeader } from '../components/PageHeader'
import { LoadingState } from '../components/LoadingState'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Alert, AlertDescription } from '@/components/ui/alert'

export function AdminUsersPage() {
  const queryClient = useQueryClient()
  const { data: users, isLoading } = useAdminListUsers()
  const updateMutation = useAdminUpdateUser()
  const [error, setError] = useState('')

  const handlePromote = async (userId: string, name: string, currentAdmin: boolean) => {
    const action = currentAdmin ? 'Remove admin from' : 'Promote'
    if (!confirm(`${action} ${name}?`)) return
    setError('')
    try {
      await updateMutation.mutateAsync({ userId, data: { is_admin: !currentAdmin } })
      queryClient.invalidateQueries({ queryKey: getAdminListUsersQueryKey() })
    } catch {
      setError(`Failed to update ${name}.`)
    }
  }

  if (isLoading) return <LoadingState />

  return (
    <div>
      <PageHeader title="Users" />

      {error && (
        <Alert variant="destructive" className="mb-4">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <Card className="overflow-hidden">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Email</TableHead>
                <TableHead>Phones</TableHead>
                <TableHead>Admin</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(users ?? []).map((user) => (
                <TableRow key={user.id}>
                  <TableCell className="font-medium">{user.name}</TableCell>
                  <TableCell className="text-muted-foreground">{user.email}</TableCell>
                  <TableCell className="text-muted-foreground">
                    {user.phone_numbers
                      ?.filter((p) => p.verified)
                      .map((p) => p.number)
                      .join(', ') || '—'}
                  </TableCell>
                  <TableCell>
                    {user.is_admin ? (
                      <Badge className="border-transparent bg-blue-100 text-blue-800 hover:bg-blue-100">
                        Admin
                      </Badge>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handlePromote(user.id, user.name, user.is_admin)}
                      disabled={updateMutation.isPending}
                      className={
                        user.is_admin
                          ? 'text-destructive hover:text-destructive'
                          : 'text-primary hover:text-primary'
                      }
                    >
                      {user.is_admin ? 'Remove admin' : 'Make admin'}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </Card>
    </div>
  )
}
