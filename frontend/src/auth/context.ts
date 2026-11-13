import { createContext } from 'react'
import type { Role, UserOut } from '../api/types'

export interface AuthValue {
  user: UserOut | null
  /** True while checking a token kept from earlier in this browser tab. */
  loading: boolean
  /** Logs in, or returns a ticket when a two-step verification code is needed next (loginSecondStep). */
  login: (username: string, password: string) => Promise<{ mfaTicket: string } | null>
  loginSecondStep: (ticket: string, code: string) => Promise<void>
  logout: () => void
  /** Asks the server who is logged in again (after the password was changed). */
  reload: () => Promise<void>
  hasRole: (...roles: Role[]) => boolean
}

export const AuthContext = createContext<AuthValue | null>(null)
