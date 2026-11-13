// Small helpers for the case screens.

import { useQuery, useQueryClient } from '@tanstack/react-query'
import { kh } from '../api'
import type { CaseDetail, CaseType } from '../types'

/** Refresh everything shown about a case after a change (its page, files, history, team...). */
export function useRefreshCase(caseId: string) {
  const queryClient = useQueryClient()
  return () => queryClient.invalidateQueries({ queryKey: ['kh', 'case', caseId] })
}

/** The case's type: its folder names and the kinds of evidence it expects. */
export function useCaseType(detail: CaseDetail): CaseType | undefined {
  const types = useQuery({ queryKey: ['kh', 'case-types'], queryFn: () => kh.caseTypes(), staleTime: 5 * 60_000 })
  return types.data?.find((t) => t.code === detail.case_type)
}

/** What is wrong with a folder name (null when it is fine or still empty): the backend's rule, letters and digits first,
 * then letters, digits, spaces and . _ - (up to 100 characters). */
export function folderNameProblem(name: string): string | null {
  const text = name.trim()
  if (!text) return null
  if (text.length > 100) return 'At most 100 characters'
  return /^[A-Za-z0-9][A-Za-z0-9 ._-]*$/.test(text) ? null : 'Use letters, digits, spaces and . _ - (starting with a letter or digit)'
}

/** A local date and time from the form, as an ISO time with this computer's UTC offset. */
export function withOffset(local: string): string | null {
  if (!local) return null
  const date = new Date(local)
  if (Number.isNaN(date.getTime())) return null
  const minutes = -date.getTimezoneOffset()
  const sign = minutes >= 0 ? '+' : '-'
  const pad = (n: number) => String(Math.floor(Math.abs(n))).padStart(2, '0')
  return `${local.length === 16 ? `${local}:00` : local}${sign}${pad(minutes / 60)}:${pad(minutes % 60)}`
}
