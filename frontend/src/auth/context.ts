import { createContext } from 'react'
import type { Role, UserOut } from '../api/types'

export interface AuthValue {
  user: UserOut | null
  /** True while checking a token kept from earlier in this browser tab. */
  loading: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => void
  hasRole: (...roles: Role[]) => boolean
}

export const AuthContext = createContext<AuthValue | null>(null)
