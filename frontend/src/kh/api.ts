// Knight Hawk (Case Management) API: one function per endpoint under /api/v1.
// The backend checks every permission; the screens only decide what to offer.

import { apiFetch } from '../api/client'
import type * as T from './types'

const e = encodeURIComponent
type Params = Record<string, string | number | boolean | null | undefined | string[]>

/** Create requests carry an Idempotency-Key: repeating one (a double click, a retry) returns the first answer. */
const once = (key?: string) => (key ? { 'Idempotency-Key': key } : undefined)
const get = <R>(path: string, params?: Params) => apiFetch<R>(`/v1${path}`, { params })
const post = <R>(path: string, json: unknown = {}, key?: string) => apiFetch<R>(`/v1${path}`, { method: 'POST', json, headers: once(key) })

export function newKey(): string {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`
}

export const kh = {
  // ------------------------------------------------------------ cases
  caseTypes: () => get<T.CaseType[]>('/case-types'),
  cases: (params: Params = {}) => get<T.CaseList>('/cases', params),
  myCases: () => get<T.MyCase[]>('/cases/mine'),
  createCase: (body: T.CaseCreate, key?: string) => post<T.CaseCreated>('/cases', body, key),
  case: (caseId: string) => get<T.CaseDetail>(`/cases/${e(caseId)}`),
  addReference: (caseId: string, body: T.OfficialReferenceIn, key?: string) =>
    post<T.OfficialReferenceOut>(`/cases/${e(caseId)}/official-references`, body, key),
  changeCaseNumber: (caseId: string, body: { number: string; reason: string }) => post<T.CaseDetail>(`/cases/${e(caseId)}/number`, body),
  changeCaseName: (caseId: string, body: { name: string; reason: string }) => post<T.CaseDetail>(`/cases/${e(caseId)}/name`, body),
  changeCaseStatus: (caseId: string, body: T.CaseStatusChange) => post<T.CaseDetail>(`/cases/${e(caseId)}/status`, body),

  // ------------------------------------------------------------ folders, files, notes, the history
  addFolder: (caseId: string, name: string, key?: string) => post<T.FolderOut>(`/cases/${e(caseId)}/folders`, { name }, key),
  files: (caseId: string, params: { folder?: string; include_withdrawn?: boolean } = {}) => get<T.FilesView>(`/cases/${e(caseId)}/files`, params),
  addNote: (caseId: string, body: T.NoteCreate, key?: string) => post<T.NoteAdded>(`/cases/${e(caseId)}/notes`, body, key),
  reviseNote: (artifactId: string, body: T.NoteRevise, key?: string) => post<T.NoteRevised>(`/artifacts/${e(artifactId)}/versions`, body, key),
  withdrawNote: (artifactId: string, reason: string) => post<T.ArtifactHistory>(`/artifacts/${e(artifactId)}/withdraw`, { reason }),
  withdrawEvidence: (evidenceId: string, reason: string) => post<T.EvidenceDetail>(`/evidence/${e(evidenceId)}/withdraw`, { reason }),
  chatThreads: (caseId: string) => get<T.ChatThread[]>(`/cases/${e(caseId)}/chat/threads`),
  chatMessages: (caseId: string, thread: string) => get<T.ChatMessages>(`/cases/${e(caseId)}/chat/messages`, { with: thread }),
  chatSend: (caseId: string, to: string | null, body: string) => post<T.ChatMessage>(`/cases/${e(caseId)}/chat/messages`, to ? { to, body } : { body }),
  chatRead: (caseId: string, thread: string, upTo: number) => post<void>(`/cases/${e(caseId)}/chat/read`, { thread, up_to: upTo }),
  history: (caseId: string, params: { limit?: number; after?: number; latest?: number } = {}) => get<T.HistoryView>(`/cases/${e(caseId)}/history`, params),
  historyCheck: (caseId: string) => get<T.HistoryCheck>(`/cases/${e(caseId)}/history/check`),

  // ------------------------------------------------------------ evidence
  addEvidence: (caseId: string, form: FormData, key?: string) =>
    apiFetch<T.EvidenceAdded>(`/v1/cases/${e(caseId)}/evidence`, { method: 'POST', body: form, headers: once(key) }),
  evidence: (evidenceId: string) => get<T.EvidenceDetail>(`/evidence/${e(evidenceId)}`),
  evidenceVersions: (evidenceId: string) => get<T.EvidenceVersions>(`/evidence/${e(evidenceId)}/versions`),
  custody: (evidenceId: string) => get<T.CustodyView>(`/evidence/${e(evidenceId)}/custody`),
  custodyAction: (evidenceId: string, body: T.CustodyAction) => post<T.CustodyView>(`/evidence/${e(evidenceId)}/custody`, body),
  verify: (evidenceId: string) => post<T.VerificationOut>(`/evidence/${e(evidenceId)}/verify`),
  downloadLink: (evidenceId: string) => post<T.DownloadLink>(`/evidence/${e(evidenceId)}/download-token`),
  preview: (evidenceId: string) => get<T.Preview>(`/evidence/${e(evidenceId)}/preview`),
  sealEvidence: (evidenceId: string, reason: string) => post<T.EvidenceDetail>(`/evidence/${e(evidenceId)}/seal`, { reason }),
  unsealEvidence: (evidenceId: string, reason: string) => post<T.EvidenceDetail>(`/evidence/${e(evidenceId)}/unseal`, { reason }),

  // ------------------------------------------------------------ stations and people
  stations: () => get<T.Station[]>('/stations'),

  peopleCapabilities: () => get<T.PeopleCapabilities>('/people/capabilities'),
  accounts: (q?: string) => get<T.AccountRow[]>('/people/accounts', { q }),
  createAccount: (body: T.AccountCreate) => post<T.AccountCreated>('/people/accounts', body),
  changeRole: (userId: string, role: string, reason: string) => post<T.AccountRow>(`/people/accounts/${e(userId)}/role`, { role, reason }),
  changeClearance: (userId: string, clearance: string, reason: string) => post<T.AccountRow>(`/people/accounts/${e(userId)}/clearance`, { clearance, reason }),
  setStations: (userId: string, stationIds: string[], reason: string) =>
    post<T.AccountRow>(`/people/accounts/${e(userId)}/stations`, { station_ids: stationIds, reason }),
  resetPassword: (userId: string, reason: string) => post<T.PasswordIssued>(`/people/accounts/${e(userId)}/reset-password`, { reason }),
  setAccountActive: (userId: string, active: boolean, reason: string) => post<T.AccountRow>(`/people/accounts/${e(userId)}/active`, { active, reason }),
  officers: (params: { q?: string; free?: boolean; station_id?: string } = {}) => get<T.OfficerOut[]>('/people/officers', { ...params, free: params.free ? 'true' : undefined }),
  addOfficer: (body: T.OfficerCreate) => post<T.OfficerOut>('/people/officers', body),
  importOfficers: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return apiFetch<T.OfficerImportResult>('/v1/people/officers/import', { method: 'POST', body: form })
  },
  peopleStations: () => get<T.StationSummary[]>('/people/stations'),
  createStation: (body: T.StationCreate) => post<T.StationSummary>('/people/stations', body),
  updateStation: (stationId: string, body: T.StationUpdate) => post<T.StationSummary>(`/people/stations/${e(stationId)}`, body),
  // ------------------------------------------------------------ station and officer dashboards
  dashboardStations: () => get<T.StationsOverview>('/dashboards/stations'),
  dashboardStation: (stationId: string) => get<T.StationDashboard>(`/dashboards/stations/${e(stationId)}`),
  dashboardOfficer: (userId: string) => get<T.OfficerDashboard>(`/dashboards/officers/${e(userId)}`),

  // ------------------------------------------------------------ the team, tasks, comments
  /** Who may be chosen: `lead` and `supervisor` when registering a case; `team` to add someone to a case. */
  colleagues: (params: { purpose: 'lead' | 'supervisor' | 'team'; classification?: string; case_id?: string; q?: string; station_id?: string }) =>
    get<T.Colleague[]>('/colleagues', params),
  team: (caseId: string) => get<T.TeamView>(`/cases/${e(caseId)}/team`),
  addMember: (caseId: string, body: T.TeamAdd) => post<T.TeamView>(`/cases/${e(caseId)}/team`, body),
  removeMember: (caseId: string, userId: string, reason: string) => post<T.TeamView>(`/cases/${e(caseId)}/team/${e(userId)}/remove`, { reason }),
  changeLead: (caseId: string, userId: string, reason: string) => post<T.CaseDetail>(`/cases/${e(caseId)}/lead`, { user_id: userId, reason }),
  accessHistory: (caseId: string) => get<T.AccessEventOut[]>(`/cases/${e(caseId)}/access-history`),
  adminAccessHistory: (caseId: string) => get<T.AccessEventOut[]>(`/admin/cases/${e(caseId)}/access-history`),
  comments: (caseId: string, targetType: string, targetId: string) =>
    get<T.CommentOut[]>(`/cases/${e(caseId)}/comments`, { target_type: targetType, target_id: targetId }),
  addComment: (caseId: string, body: T.CommentCreate, key?: string) => post<T.CommentOut>(`/cases/${e(caseId)}/comments`, body, key),

  artifactVersions: (artifactId: string) => get<T.ArtifactHistory>(`/artifacts/${e(artifactId)}/versions`),
  sealArtifact: (artifactId: string, reason: string) => post<T.ArtifactHistory>(`/artifacts/${e(artifactId)}/seal`, { reason }),
  unsealArtifact: (artifactId: string, reason: string) => post<T.ArtifactHistory>(`/artifacts/${e(artifactId)}/unseal`, { reason }),

  // ------------------------------------------------------------ notices, links, reports
  notifications: (params: Params = {}) => get<T.NotificationList>('/notifications', params),
  readNotification: (id: number) => post<T.NotificationOut>(`/notifications/${id}/read`),
  readAllNotifications: () => post<{ marked: number }>('/notifications/read-all'),
  myContributions: () => get<T.MyContributions>('/contributions/mine'),
  links: (caseId: string) => get<T.CaseLinks>(`/cases/${e(caseId)}/links`),
  addLink: (caseId: string, body: T.LinkCreate, key?: string) => post<T.LinkAdded>(`/cases/${e(caseId)}/links`, body, key),
  reportPreview: (caseId: string) => get<T.ReportPreview>(`/cases/${e(caseId)}/report-preview`),

  // ------------------------------------------------------------ Case Intelligence inside a case
  intelligence: (caseId: string) => get<T.IntelligenceStatus>(`/cases/${e(caseId)}/intelligence`),
  prepareIntelligence: (caseId: string) => post<T.IntelligenceStatus>(`/cases/${e(caseId)}/intelligence/prepare`, {}),
  searchCase: (caseId: string, body: T.CaseSearchRequest) => post<T.CaseSearchResponse>(`/cases/${e(caseId)}/intelligence/search`, body),
  similarCases: (caseId: string, params: Params = {}) => get<T.CaseSimilarResponse>(`/cases/${e(caseId)}/intelligence/similar`, params),
  askCase: (caseId: string, body: T.AskRequest) => post<T.CaseAnswer>(`/cases/${e(caseId)}/intelligence/ask`, body),
  offences: (caseId: string) => get<T.OffenceSuggestions>(`/cases/${e(caseId)}/intelligence/offences`),
  timeline: (caseId: string) => get<T.TimelineView>(`/cases/${e(caseId)}/intelligence/timeline`),
  rebuildTimeline: (caseId: string, body: T.TimelineRebuild, key?: string) =>
    post<T.TimelineRebuilt>(`/cases/${e(caseId)}/intelligence/timeline`, body, key),

  // ------------------------------------------------------------ integrations
  integrationContract: () => get<T.IntegrationContract>('/integrations/contract'),
  imports: (caseId: string) => get<T.ImportsView>(`/cases/${e(caseId)}/imports`),
  importDetail: (caseId: string, artifactId: string) => get<T.ImportDetail>(`/cases/${e(caseId)}/imports/${e(artifactId)}`),
  indicators: (caseId: string) => get<T.IndicatorsView>(`/cases/${e(caseId)}/indicators`),
  testSource: () => get<T.TestSourceView>('/integrations/test-source'),
  sendTestFinding: (body: T.TestSourceSend, key?: string) => post<T.ImportAdded>('/integrations/test-source/send', body, key),
  integrationSources: () => get<T.IntegrationSourceOut[]>('/integrations/sources'),
  registerSource: (body: T.SourceCreate) => post<T.SourceKeyIssued>('/integrations/sources', body),
  registerTestSource: () => post<T.SourceKeyIssued>('/integrations/sources/test-source'),
  changeSourceStatus: (sourceId: string, enabled: boolean, reason: string) =>
    post<T.IntegrationSourceOut>(`/integrations/sources/${e(sourceId)}/status`, { enabled, reason }),
  rotateSourceKey: (sourceId: string, reason: string) => post<T.SourceKeyIssued>(`/integrations/sources/${e(sourceId)}/key`, { reason }),

  // ------------------------------------------------------------ reports and governance
  reports: (caseId: string) => get<T.ReportsView>(`/cases/${e(caseId)}/reports`),
  generateReport: (caseId: string, body: T.ReportCreate, key?: string) => post<T.ReportGenerated>(`/cases/${e(caseId)}/reports`, body, key),
  reportDownloadLink: (exportId: string) => post<T.DownloadLink>(`/reports/${e(exportId)}/download-link`),
  verifyReport: (exportId: string) => post<T.ReportCheck>(`/reports/${e(exportId)}/verify`),
  verifyReportFile: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return apiFetch<T.ReportCheck>('/v1/reports/verify-file', { method: 'POST', body: form })
  },
  caseGovernance: (caseId: string) => get<T.CaseGovernance>(`/cases/${e(caseId)}/governance`),
  placeHold: (caseId: string, body: T.LegalHoldCreate) => post<T.LegalHoldOut>(`/cases/${e(caseId)}/legal-holds`, body),
  releaseHold: (holdId: string, reason: string) => post<T.LegalHoldOut>(`/legal-holds/${e(holdId)}/release`, { reason }),
  proposeRetention: (caseId: string, body: T.RetentionDecisionCreate) => post<T.RetentionDecisionOut>(`/cases/${e(caseId)}/retention-decisions`, body),
  decideRetention: (decisionId: string, approve: boolean, note: string) =>
    post<T.RetentionDecisionOut>(`/retention-decisions/${e(decisionId)}/decide`, { approve, note }),

  // ------------------------------------------------------------ CDR Analysis
  cdrBatches: (caseId: string) => get<T.CdrImportBatch[]>(`/cdr/cases/${e(caseId)}/batches`),
  cdrBatch: (caseId: string, batchId: string) => get<T.CdrImportBatch>(`/cdr/cases/${e(caseId)}/batches/${e(batchId)}`),
  cdrUpload: (caseId: string, file: File, msisdnRule: string, sourceTimezone: string) => {
    const form = new FormData()
    form.append('file', file)
    form.append('msisdn_rule', msisdnRule)
    form.append('source_timezone', sourceTimezone)
    return apiFetch<T.CdrImportBatch>(`/v1/cdr/cases/${e(caseId)}/batches`, { method: 'POST', body: form })
  },
  cdrRecords: (caseId: string, params: Params = {}) => get<T.CdrRecordList>(`/cdr/cases/${e(caseId)}/records`, params),
  cdrSummary: (caseId: string) => get<T.CdrSummary>(`/cdr/cases/${e(caseId)}/analytics/summary`),
  cdrTopContacts: (caseId: string, limit = 20) => get<T.CdrTopContact[]>(`/cdr/cases/${e(caseId)}/analytics/top-contacts`, { limit }),
  cdrCallGraph: (caseId: string, minCalls = 1) => get<T.CdrCallGraph>(`/cdr/cases/${e(caseId)}/analytics/call-graph`, { min_calls: minCalls }),
  cdrFrequencyByHour: (caseId: string) => get<T.CdrHourFrequency[]>(`/cdr/cases/${e(caseId)}/analytics/frequency-by-hour`),
  cdrCustody: (caseId: string, batchId: string) =>
    get<T.CdrCustodyEvent[]>(`/cdr/cases/${e(caseId)}/batches/${e(batchId)}/custody`),

  // ------------------------------------------------------------ CDR Advanced Analysis (Features 4, 6-12)
  cdrTimeline: (caseId: string, number: string, params: Params = {}) =>
    get<T.CdrRecordList>(`/cdr/cases/${e(caseId)}/analytics/timeline`, { number, ...params }),
  cdrCommonContacts: (caseId: string, a: string, b: string) =>
    get<T.CdrCommonContacts>(`/cdr/cases/${e(caseId)}/analytics/common-contacts`, { a, b }),
  cdrImeiAssociations: (caseId: string) =>
    get<T.CdrImeiAssociations>(`/cdr/cases/${e(caseId)}/analytics/imei-associations`),
  cdrAnomalies: (caseId: string) =>
    get<T.CdrAnomaly[]>(`/cdr/cases/${e(caseId)}/analytics/anomalies`),
  cdrLinkGraph: (caseId: string, number: string, hops = 2, minCalls = 1) =>
    get<T.CdrLinkGraph>(`/cdr/cases/${e(caseId)}/analytics/link-graph`, { number, hops, min_calls: minCalls }),
  cdrDataProfile: (caseId: string) =>
    get<T.CdrDataProfile>(`/cdr/cases/${e(caseId)}/data-profile`),
  cdrLlmSearch: (caseId: string, query: string) =>
    apiFetch<T.CdrLlmResult>(`/v1/cdr/cases/${e(caseId)}/llm-search`, { method: 'POST', json: { query } }),
  cdrExportCsv: async (caseId: string): Promise<void> => {
    const blob = await apiFetch<Blob>(`/v1/cdr/cases/${e(caseId)}/export.csv`, { as: 'blob' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `cdr-${caseId.slice(0, 8)}.csv`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  },
  cdrExportToCase: (caseId: string) =>
    apiFetch<T.CdrExportResult>(`/v1/cdr/cases/${e(caseId)}/export-to-case`, { method: 'POST', json: {} }),

  // ------------------------------------------------------------ administration
  adminOverview: () => get<T.AdminOverview>('/admin/overview'),
  registry: (params: Params = {}) => get<T.Registry>('/admin/cases', params),
  caseAudit: (caseId: string, params: Params = {}) => get<T.CaseAudit>(`/admin/cases/${e(caseId)}/audit`, params),
  integrityReport: (params: Params = {}) => get<T.IntegrityReport>('/admin/evidence-integrity', params),
}
