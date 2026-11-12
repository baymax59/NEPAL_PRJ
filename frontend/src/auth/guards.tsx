import { Alert, Center, Loader } from '@mantine/core'
import { IconLock } from '@tabler/icons-react'
import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router'
import type { Role } from '../api/types'
import { useAuth } from './useAuth'

/** Shows its content only to a logged-in user; everyone else goes to the login page. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) {
    return (
      <Center h="100vh">
        <Loader />
      </Center>
    )
  }
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  return children
}

/** Hides a page from roles that may not use it. The backend enforces this too: this is for clarity. */
export function RequireRole({ roles, children }: { roles: Role[]; children: ReactNode }) {
  const { user } = useAuth()
  if (!user || !roles.includes(user.role)) {
    return (
      <Alert color="gray" icon={<IconLock size={18} />} title="Not available for your role">
        Your role ({user?.role}) does not include this page. Ask an administrator if you need it.
      </Alert>
    )
  }
  return children
}
