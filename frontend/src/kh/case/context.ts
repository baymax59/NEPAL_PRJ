import { createContext, useContext } from 'react'
import type { CaseDetail } from '../types'

export const CaseContext = createContext<CaseDetail | null>(null)

/** The case open in the workspace (provided by CaseLayout). */
export function useCase(): CaseDetail {
  const value = useContext(CaseContext)
  if (!value) throw new Error('useCase() is only available inside a case page')
  return value
}
