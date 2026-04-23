import { useState } from 'react'
import { Link, NavLink, useNavigate } from 'react-router-dom'
import { Disc3, LogOut, Menu, User } from 'lucide-react'
import { useAuth } from '../auth/AuthContext'
import { useGetMe } from '../api/northlanding'
import { Button, buttonVariants } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from '@/components/ui/sheet'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { cn } from '@/lib/utils'

interface NavItem {
  to: string
  label: string
}

function getInitials(name?: string | null) {
  if (!name) return '?'
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((n) => n[0]?.toUpperCase() ?? '')
    .join('')
}

export function Navbar() {
  const { isAuthenticated, logout } = useAuth()
  const { data: user } = useGetMe({ query: { enabled: isAuthenticated } })
  const navigate = useNavigate()
  const [mobileOpen, setMobileOpen] = useState(false)

  const handleLogout = () => {
    logout()
    setMobileOpen(false)
    navigate('/')
  }

  const userLinks: NavItem[] = [
    { to: '/my/discs', label: 'My Discs' },
    { to: '/my/wishlist', label: 'Wishlist' },
  ]

  const adminLinks: NavItem[] = [
    { to: '/admin/discs', label: 'Discs' },
    { to: '/admin/pickup-events', label: 'Pickup Events' },
    { to: '/admin/users', label: 'Users' },
  ]

  const desktopLink = (item: NavItem) => (
    <NavLink
      key={item.to}
      to={item.to}
      className={({ isActive }) =>
        cn(
          buttonVariants({ variant: isActive ? 'secondary' : 'ghost', size: 'sm' }),
          'font-medium',
        )
      }
    >
      {item.label}
    </NavLink>
  )

  const mobileLink = (item: NavItem) => (
    <NavLink
      key={item.to}
      to={item.to}
      onClick={() => setMobileOpen(false)}
      className={({ isActive }) =>
        cn(
          'block rounded-md px-3 py-2 text-sm font-medium',
          isActive
            ? 'bg-secondary text-secondary-foreground'
            : 'text-foreground hover:bg-muted',
        )
      }
    >
      {item.label}
    </NavLink>
  )

  return (
    <nav className="sticky top-0 z-40 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4 sm:px-6 lg:px-8">
        <Link to="/" className="flex items-center gap-2 font-semibold text-foreground">
          <Disc3 className="h-6 w-6 text-primary" aria-hidden="true" />
          <span>North Landing Discs</span>
        </Link>

        {isAuthenticated && (
          <>
            <div className="hidden items-center gap-1 md:flex">
              {userLinks.map(desktopLink)}
              {user?.is_admin && (
                <>
                  <span className="mx-2 h-5 w-px bg-border" aria-hidden="true" />
                  {adminLinks.map(desktopLink)}
                </>
              )}
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="sm" className="ml-2 gap-2 px-2">
                    <Avatar className="h-7 w-7">
                      <AvatarFallback className="bg-primary text-xs text-primary-foreground">
                        {getInitials(user?.name)}
                      </AvatarFallback>
                    </Avatar>
                    <span className="hidden lg:inline">{user?.name ?? '…'}</span>
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-48">
                  <DropdownMenuLabel>{user?.name ?? 'Account'}</DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={() => navigate('/my/profile')}>
                    <User className="mr-2 h-4 w-4" /> Profile
                  </DropdownMenuItem>
                  <DropdownMenuItem onClick={handleLogout}>
                    <LogOut className="mr-2 h-4 w-4" /> Logout
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>

            <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
              <SheetTrigger asChild>
                <Button variant="ghost" size="icon" className="md:hidden" aria-label="Open menu">
                  <Menu className="h-5 w-5" />
                </Button>
              </SheetTrigger>
              <SheetContent side="right" className="w-72">
                <SheetHeader>
                  <SheetTitle>Menu</SheetTitle>
                </SheetHeader>
                <div className="mt-6 flex flex-col gap-1">
                  {userLinks.map(mobileLink)}
                  <NavLink
                    to="/my/profile"
                    onClick={() => setMobileOpen(false)}
                    className={({ isActive }) =>
                      cn(
                        'block rounded-md px-3 py-2 text-sm font-medium',
                        isActive
                          ? 'bg-secondary text-secondary-foreground'
                          : 'text-foreground hover:bg-muted',
                      )
                    }
                  >
                    Profile
                  </NavLink>
                  {user?.is_admin && (
                    <>
                      <div className="my-2 border-t border-border" />
                      <p className="px-3 pb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                        Admin
                      </p>
                      {adminLinks.map(mobileLink)}
                    </>
                  )}
                  <div className="my-2 border-t border-border" />
                  <button
                    onClick={handleLogout}
                    className="flex items-center rounded-md px-3 py-2 text-left text-sm font-medium text-foreground hover:bg-muted"
                  >
                    <LogOut className="mr-2 h-4 w-4" />
                    Logout {user?.name ? `(${user.name})` : ''}
                  </button>
                </div>
              </SheetContent>
            </Sheet>
          </>
        )}
      </div>
    </nav>
  )
}
