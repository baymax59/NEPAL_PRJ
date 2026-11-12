// One function per backend endpoint.

import { apiFetch } from './client'
import type {
  AuditPage,
  CaseDetail,
  CaseFilters,
  CaseList,
  ChatAnswer,
  ChatTurn,
  CdrSession,
  FilterOptions,
  MatchExplanation,
  SearchRequest,
  SearchResponse,
  SimilarCasesResponse,
  TokenOut,
  UploadOut,
  UserOut,
} from './types'

const id = (value: string) => encodeURIComponent(value)

export const login = (username: string, password: string) =>
  apiFetch<TokenOut>('/auth/token', {
    method: 'POST',
    body: new URLSearchParams({ username, password }),
    isLogin: true,
  })

export const getMe = () => apiFetch<UserOut>('/auth/me')

export const listCases = (params: Record<string, string | number | null | undefined | string[]>) =>
  apiFetch<CaseList>('/cases', { params })

export const getFilterOptions = () => apiFetch<FilterOptions>('/cases/filters')

export const getCase = (displayId: string) => apiFetch<CaseDetail>(`/cases/${id(displayId)}`)

// Search text goes in the request body, never the URL (URLs end up in logs).
export const search = (request: SearchRequest) => apiFetch<SearchResponse>('/search', { method: 'POST', json: request })

export const explainCase = (displayId: string, query: string) =>
  apiFetch<MatchExplanation>(`/cases/${id(displayId)}/explain`, { method: 'POST', json: { query } })

// Can take 1-3 minutes: the model runs on this computer. The question goes in the body, never the URL.
export const askAboutCase = (displayId: string, question: string, history: ChatTurn[], compareWith?: string) =>
  apiFetch<ChatAnswer>(`/cases/${id(displayId)}/chat`, {
    method: 'POST',
    json: { question, history, compare_with: compareWith || null },
  })

export const similarToCase = (displayId: string, filters: CaseFilters, limit = 10) =>
  apiFetch<SimilarCasesResponse>(`/cases/${id(displayId)}/similar`, {
    params: { year_from: filters.year_from, year_to: filters.year_to, outcome: filters.outcome, limit },
  })

export const uploadCase = (file: File) => {
  const body = new FormData()
  body.append('file', file)
  return apiFetch<UploadOut>('/uploads', { method: 'POST', body })
}

export const getUpload = (uploadId: string) => apiFetch<UploadOut>(`/uploads/${id(uploadId)}`)

export const similarToUpload = (uploadId: string, filters: CaseFilters, limit = 10) =>
  apiFetch<SimilarCasesResponse>(`/uploads/${id(uploadId)}/similar`, { method: 'POST', json: { filters, limit } })

export const deleteUpload = (uploadId: string) => apiFetch<void>(`/uploads/${id(uploadId)}`, { method: 'DELETE' })

export const getAuditLog = (params: Record<string, string | number | null | undefined>) =>
  apiFetch<AuditPage>('/audit', { params })

export const getCdrSession = (caseId: string) =>
  apiFetch<CdrSession>(`/cdr/session?case_id=${encodeURIComponent(caseId)}`)
