import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { setUnauthorizedHandler, tokenStore } from '../api/client'
import { getMe, login as loginRequest } from '../api/endpoints'
import type { UserOut } from '../api/types'
import { AuthContext, type AuthValue } from './context'

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [user, setUser] = useState<UserOut | null>(null)
  const [loading, setLoading] = useState(() => tokenStore.get() !== null)

  const forget = useCallback(() => {
    tokenStore.clear()
    setUser(null)
    queryClient.clear() // no case data stays in memory after logout
  }, [queryClient])

  useEffect(() => setUnauthorizedHandler(forget), [forget])

  useEffect(() => {
    if (!tokenStore.get()) return
    getMe()
      .then(setUser)
      .catch(() => tokenStore.clear())
      .finally(() => setLoading(false))
  }, [])

  const login = useCallback(async (username: string, password: string) => {
    const token = await loginRequest(username, password)
    tokenStore.set(token.access_token)
    setUser(await getMe())
  }, [])

  const value = useMemo<AuthValue>(
    () => ({
      user,
      loading,
      login,
      logout: forget,
      hasRole: (...roles) => user !== null && roles.includes(user.role),
    }),
    [user, loading, login, forget],
  )
  return <AuthContext value={value}>{children}</AuthContext>
}
