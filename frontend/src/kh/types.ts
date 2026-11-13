// Knight Hawk (Case Management) types, generated from the backend's API description (src/api/schema.d.ts).
// Regenerate after a backend change: `uv run python -m scripts.export_openapi ../docs/case-management/openapi.json` (in backend/),
// then `npm run gen:api` (in frontend/).

import type { components } from '../api/schema'

type S = components['schemas']

export type Person = S['Person']
export type CaseRef = S['CaseRef']
export type CaseType = S['CaseType']
export type CaseCreate = S['CaseCreate']
export type CaseCreated = S['CaseCreated']
export type CaseSummary = S['app__casemgmt__schemas__CaseSummary']
export type CaseList = S['app__casemgmt__schemas__CaseList']
export type CaseDetail = S['app__casemgmt__schemas__CaseDetail']
export type CaseStatusChange = S['CaseStatusChange']
export type OfficialReferenceIn = S['OfficialReferenceIn']
export type OfficialReferenceOut = S['OfficialReferenceOut']
export type StatusEventOut = S['StatusEventOut']
export type Registry = S['Registry']
export type RegistryItem = S['RegistryItem']
export type CaseAudit = S['CaseAudit']
export type AuditEntry = S['AuditEntry']

// The plain case: folders, files, the history and the team.
export type FolderOut = S['FolderOut']
export type FolderCreate = S['FolderCreate']
export type FileOut = S['FileOut']
export type FilesView = S['FilesView']
export type HistoryEntry = S['EntryOut']
export type HistoryView = S['HistoryView']
export type HistoryCheck = S['HistoryCheck']
export type TeamView = S['TeamView']
export type TeamMemberOut = S['TeamMemberOut']
export type TeamAdd = S['TeamAdd']
export type LeadChange = S['LeadChange']
export type NoteCreate = S['NoteCreate']
export type NoteAdded = S['NoteAdded']
export type NoteRevise = S['NoteRevise']
export type NoteRevised = S['NoteRevised']
export type ArtifactVersionOut = S['ArtifactVersionOut']
export type MyCase = S['MyCase']
export type ChatThread = S['ChatThread']
export type ChatMessage = S['ChatMessageOut']
export type ChatMessages = S['ChatMessages']
export type EntryWithCase = S['EntryWithCase']
export type EvidenceSummary = S['EvidenceSummary']
export type EvidenceVersionOut = S['EvidenceVersionOut']
export type LinkTypeOut = S['LinkTypeOut']
export type ReportTypeInfo = S['ReportTypeInfo']

export type EvidenceAdded = S['EvidenceAdded']
export type EvidenceDetail = S['EvidenceDetail']
export type EvidenceVersions = S['EvidenceVersions']
export type CustodyView = S['CustodyView']
export type CustodyEventOut = S['CustodyEventOut']
export type CustodyAction = S['CustodyAction']
export type Custodian = S['Custodian']
export type VerificationOut = S['VerificationOut']
export type IntegrityCheckOut = S['IntegrityCheckOut']
export type DownloadLink = S['DownloadLink']
export type Preview = S['Preview']
export type IntegrityReport = S['IntegrityReport']

export type AccessEventOut = S['AccessEventOut']
export type TaskCreate = S['TaskCreate']
export type TaskOut = S['TaskOut']
export type TaskDetail = S['TaskDetail']
export type TaskStatusChange = S['TaskStatusChange']
export type CommentOut = S['CommentOut']
export type CommentCreate = S['CommentCreate']
export type ArtifactHistory = S['ArtifactHistory']
export type NotificationOut = S['NotificationOut']
export type NotificationList = S['NotificationList']

export type Colleague = S['Colleague']
export type Station = S['StationOut']
export type AccountRow = S['AccountRow']
export type PeopleCapabilities = S['Capabilities']
export type AccountCreate = S['AccountCreate']
export type AccountCreated = S['AccountCreated']
export type PasswordIssued = S['PasswordIssued']
export type OfficerOut = S['OfficerOut']
export type OfficerCreate = S['OfficerCreate']
export type OfficerImportResult = S['ImportResult']
export type StationSummary = S['StationSummary']
export type StationCreate = S['StationCreate']
export type StationUpdate = S['StationUpdate']
export type AdminOverview = S['AdminOverview']
export type StationsOverview = S['StationsOverview']
export type StationDashboard = S['StationDashboard']
export type OfficerDashboard = S['OfficerDashboard']
export type CaseFigures = S['CaseFigures']
export type MyContributions = S['MyContributions']
export type CaseLinks = S['CaseLinks']
export type OutgoingLink = S['OutgoingLink']
export type IncomingLink = S['IncomingLink']
export type LinkCreate = S['LinkCreate']
export type LinkAdded = S['LinkAdded']
export type ReportPreview = S['ReportPreview']
export type KnowledgeCaseRef = S['KnowledgeCaseRef']

// Case Intelligence inside cases (CM-5)
export type CISource = S['CISource']
export type Coverage = S['Coverage']
export type IntelligenceStatus = S['IntelligenceStatus']
export type CaseSearchRequest = S['CaseSearchRequest']
export type CaseSearchResponse = S['CaseSearchResponse']
export type CaseSearchResult = S['CaseSearchResult']
export type CaseSimilarResponse = S['CaseSimilarResponse']
export type SimilarInvestigation = S['SimilarInvestigation']
export type KnowledgeMatch = S['KnowledgeMatch']
export type InvestigationPair = S['InvestigationPair']
export type AskRequest = S['AskRequest']
export type CaseAnswer = S['CaseAnswer']
export type AnswerSource = S['AnswerSource']
export type OffenceSuggestions = S['OffenceSuggestions']
export type OffenceCited = S['OffenceCited']
export type OffenceSuggestion = S['OffenceSuggestion']
export type TimelineView = S['TimelineView']
export type Timeline = S['Timeline']
export type TimelineEvent = S['TimelineEvent']
export type TimelineRebuild = S['TimelineRebuild']
export type TimelineRebuilt = S['TimelineRebuilt']


// Integrations (CM-6)
export type IntegrationContract = S['IntegrationContract']
export type ItemTypeInfo = S['ItemTypeInfo']
export type ImportItem = S['ImportItem']
export type ImportsView = S['ImportsView']
export type ImportDetail = S['ImportDetail']
export type ImportAdded = S['ImportAdded']
export type IdentifierDetail = S['IdentifierDetail']
export type OtherCase = S['OtherCase']
export type IndicatorRow = S['IndicatorRow']
export type IndicatorsView = S['IndicatorsView']
export type IntegrationSourceOut = S['IntegrationSourceOut']
export type SourceCreate = S['SourceCreate']
export type SourceKeyIssued = S['SourceKeyIssued']
export type TestFinding = S['TestFinding']
export type TestSourceView = S['TestSourceView']
export type TestSourceSend = S['TestSourceSend']
export type ReportImport = S['ReportImport']

// Reports and governance (CM-7)
export type ReportCreate = S['ReportCreate']
export type ReportVersion = S['ReportVersion']
export type ReportsView = S['ReportsView']
export type ReportGenerated = S['ReportGenerated']
export type ReportDetail = S['ReportDetail']
export type ReportCheck = S['ReportCheck']
export type LegalHoldCreate = S['LegalHoldCreate']
export type LegalHoldOut = S['LegalHoldOut']
export type CaseGovernance = S['CaseGovernance']
export type RetentionDecisionCreate = S['RetentionDecisionCreate']
export type RetentionDecisionOut = S['RetentionDecisionOut']
export type RetentionOverview = S['RetentionOverview']
export type RetentionPolicyCreate = S['RetentionPolicyCreate']
export type RetentionPolicyOut = S['RetentionPolicyOut']
export type GovernanceOverview = S['GovernanceOverview']
export type JobRunOut = S['JobRunOut']
export type CheckpointOut = S['CheckpointOut']
export type MfaStatus = S['MfaStatus']
export type MfaSetup = S['MfaSetup']

// CDR Analysis (CDR module)
export interface CdrImportBatch {
  id: string
  case_family_id: string
  uploaded_by: string
  file_name: string
  file_size_bytes: number
  file_hash_sha256: string
  record_format: string
  msisdn_rule: string
  source_timezone: string
  status: 'pending' | 'processing' | 'completed' | 'completed_with_errors' | 'failed'
  total_rows: number | null
  accepted_rows: number | null
  rejected_rows: number | null
  duplicate_rows: number | null
  import_notes: string | null
  created_at: string
  completed_at: string | null
}

export interface CdrRecord {
  id: string
  import_batch_id: string
  source_row_number: number
  is_duplicate: boolean
  a_party: string | null
  b_party: string | null
  a_party_canonical: string | null
  b_party_canonical: string | null
  timestamp_utc: string | null
  duration_seconds: number | null
  call_type: string | null
  call_direction: 'incoming' | 'outgoing' | null
  service_type: 'voice' | 'sms' | 'data' | null
  imei: string | null
  imsi: string | null
  cell_id: string | null
  area_code: string | null
  operator: string | null
  network_type: string | null
  network_generation: '2G' | '3G' | '4G' | '5G' | null
}

export interface CdrRecordList {
  total: number
  items: CdrRecord[]
}

export interface CdrTopContact {
  number: string
  count: number
}

export interface CdrGraphNode {
  id: string
  label: string
  hop?: number  // 0 = seed, 1 = direct contact, 2 = indirect
  call_count?: number
}

export interface CdrGraphEdge {
  source: string
  target: string
  count: number
  call_count?: number
  types: string[]
  total_duration_seconds?: number
}

export interface CdrCallGraph {
  nodes: CdrGraphNode[]
  edges: CdrGraphEdge[]
}

export interface CdrHourFrequency {
  hour: number
  count: number
}

export interface CdrSummary {
  total_records: number
  unique_subscribers: number
  earliest: string | null
  latest: string | null
}

export interface CdrCustodyEvent {
  event_type: string
  occurred_at: string
  actor_type: string
  details: Record<string, unknown>
}

// ── CDR Advanced Analysis types ───────────────────────────────────────────

export interface CdrColocEvent {
  cell_id: string
  time_a: string
  time_b: string
  gap_minutes: number
}

export interface CdrCommonContacts {
  number_a: string
  number_b: string
  shared_contacts: string[]
  shared_contact_count: number
  colocation_events: CdrColocEvent[]
  contacts_a_count: number
  contacts_b_count: number
}

export interface CdrImeiEntry {
  imei: string
  numbers: string[]
  number_count: number
  first_seen: string | null
  last_seen: string | null
  flagged: boolean
}

export interface CdrMultiImeiNumber {
  number: string
  imeis: string[]
  imei_count: number
}

export interface CdrImeiAssociations {
  imei_table: CdrImeiEntry[]
  multi_imei_numbers: CdrMultiImeiNumber[]
  total_imeis: number
  flagged_imeis: number
}

export interface CdrAnomaly {
  type: string
  severity: 'high' | 'medium' | 'low'
  number?: string
  imei?: string
  description: string
  imeis?: string[]
  numbers?: string[]
  cell_from?: string
  cell_to?: string
  event_count?: number
  [key: string]: unknown
}

export interface CdrLinkGraph {
  nodes: CdrGraphNode[]
  edges: CdrGraphEdge[]
  seed: string
  total_nodes: number
}

export interface CdrDataProfile {
  total_records: number
  has_data: boolean
  columns_present: string[]
  date_range: { earliest: string; latest: string } | null
  unique_number_count: number
  top_numbers: { number: string; event_count: number }[]
  service_type_counts: Record<string, number>
  direction_counts: Record<string, number>
  duration_stats: { min_seconds: number; max_seconds: number; avg_seconds: number } | null
  unique_imeis: string[]
  unique_cell_ids: string[]
}

export interface CdrLlmResult {
  mode: 'filter' | 'direct'
  narrative: string
  filters: Record<string, unknown>
  total: number
  items: CdrRecord[]
  data_profile?: { total_records: number; date_range: { earliest: string; latest: string } | null }
}

export interface CdrExportResult {
  artifact_id: string
  display_id: string
  title: string
  message: string
}
