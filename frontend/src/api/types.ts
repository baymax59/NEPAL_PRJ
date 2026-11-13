// Shapes of the backend API's requests and responses (see backend/app/schemas/).
// null means "not available in the source" — the UI must show it as such, never fill it in.

export type Role = 'viewer' | 'analyst' | 'admin'

export interface UserOut {
  id: string
  username: string
  display_name: string
  role: Role
  clearance: string
  /** Case Management organisation role: super_admin, administrator, supervisor, investigator, sub_investigator, analyst or viewer. */
  org_role: string
  organization_id: string | null
  /** This login included a two-step verification code (CM-7). */
  mfa_verified?: boolean
  /** A temporary password is in use: only 'who am I' and 'set my own password' answer until it is changed. */
  must_change_password?: boolean
  /** The person's own profile: empty until they fill it in (profile_updated_at is null until they save it once). */
  email?: string | null
  phone?: string | null
  job_title?: string | null
  profile_updated_at?: string | null
  /** Set when the person has a profile photo (fetched with GET /auth/photo/{id}). */
  photo_updated_at?: string | null
}

export interface Profile {
  username: string
  display_name: string
  org_role: string
  clearance: string
  officer_number: string | null
  rank: string | null
  stations: string[]
  email: string | null
  phone: string | null
  job_title: string | null
  profile_updated_at: string | null
  id?: string | null
  photo_updated_at?: string | null
}

export interface ProfileIn {
  email: string | null
  phone: string | null
  job_title: string | null
}

/** An officer creating their own login: the role, clearance and station are never asked for here. */
export interface RegisterIn {
  officer_number: string
  full_name: string
  username: string
  password: string
  email?: string | null
  phone?: string | null
}

export interface RegisteredOut {
  username: string
  display_name: string
  org_role: string
  station: string
  message: string
}

export interface TokenOut {
  access_token: string
  token_type: string
  expires_in: number
  /** Two-step verification: the password was right; send the ticket and a code to /auth/mfa/login. */
  mfa_required?: boolean
  mfa_ticket?: string | null
}

export interface CaseSummary {
  display_id: string
  title: string | null
  category: string | null
  court_or_agency: string | null
  status: string | null
  outcome: string | null
  primary_date: string | null
  primary_date_kind: string | null
  source_system: string
  reference_numbers: Record<string, string>
  sensitivity: string
  processing_status: string
  missing_fields: string[]
}

export interface CaseList {
  total: number
  items: CaseSummary[]
}

export interface PersonRef {
  role: string
  name: string
}

export interface CaseDate {
  kind: string
  value: string
  source_field: string
}

export interface ProvisionCitation {
  key: string
  label: string
  mentions: number
  pages: number[]
}

export interface DocumentOut {
  id: string
  doc_type: string
  title: string | null
  language: string | null
  doc_date: string | null
  page_count: number | null
  mime_type: string | null
  source_uri: string
  extraction_status: string
  extraction_warnings: string[]
  extractor: string | null
}

export interface TimelineEvent {
  event_type: 'judgment' | 'order_under_appeal' | 'dated_mention' | 'other'
  event_date: string | null
  date_text: string | null
  description: string
  document_id: string | null
  page_number: number | null
  source_excerpt: string | null
  extraction_method: string
}

export interface CaseDetail extends CaseSummary {
  source_record_id: string
  dates: CaseDate[]
  summary: string | null
  parties: PersonRef[]
  officials: PersonRef[]
  provisions: ProvisionCitation[]
  courts: { name: string; mentions: number; pages: number[] }[]
  outcome_source_field: string | null
  outcome_date: string | null
  timeline: TimelineEvent[]
  documents: DocumentOut[]
  warnings: string[]
  provenance: Record<string, unknown>
  source_extra: Record<string, unknown>
  attribution: string | null
  created_at: string
  updated_at: string
}

export interface CountedValue {
  value: string
  count: number
}

export interface FilterOptions {
  years: { min: number; max: number } | null
  outcomes: CountedValue[]
  source_systems: CountedValue[]
}

export interface CaseFilters {
  year_from?: number | null
  year_to?: number | null
  outcome?: string[]
}

export type SearchMode = 'hybrid' | 'keyword' | 'semantic'

export interface SnippetPart {
  text: string
  match: boolean
}

export interface Passage {
  chunk_id: number
  document_id: string
  page_start: number | null
  page_end: number | null
  snippet: SnippetPart[]
  matched_by: ('keyword' | 'semantic')[]
  similarity: number | null
}

export interface SearchRequest {
  query: string
  filters?: CaseFilters
  mode?: SearchMode
  limit?: number
  offset?: number
}

export interface SearchHit {
  case: CaseSummary
  relevance: number
  match_type: 'keyword+semantic' | 'keyword' | 'semantic'
  keyword_rank: number | null
  semantic_similarity: number | null
  matching_passages: number
  reasons: string[]
  passages: Passage[]
}

export interface SearchResponse {
  query: string
  mode: SearchMode
  total_cases: number
  results: SearchHit[]
  notices: string[]
  relevance_note: string
}

export interface TermMatch {
  term: string
  passages: number
}

export interface MatchExplanation {
  case: CaseSummary
  query: string
  reasons: string[]
  shared_terms: TermMatch[]
  missing_terms: string[]
  shared_provisions: ProvisionCitation[]
  provisions_only_in_query: string[]
  case_provisions: ProvisionCitation[]
  passages: Passage[]
  differences: string[]
  notices: string[]
  method_note: string
}

export interface UploadOut {
  id: string
  filename: string
  size_bytes: number
  mime_type: string
  page_count: number | null
  passages: number
  provisions: ProvisionCitation[]
  warnings: string[]
  created_at: string
}

export interface PassageExcerpt {
  page_start: number | null
  page_end: number | null
  text: string
}

export interface PassagePair {
  similarity: number
  new_case: PassageExcerpt
  similar_case: PassageExcerpt
  similar_case_chunk_id: number
  similar_case_document_id: string
}

export interface SimilarCase {
  case: CaseSummary
  relevance: number
  match_type: 'text+provisions' | 'text' | 'provisions'
  text_similarity: number | null
  matched_passages: number
  shared_provisions: string[]
  provisions_only_in_new_case: string[]
  provisions_only_in_this_case: string[]
  reasons: string[]
  differences: string[]
  passage_pairs: PassagePair[]
}

export interface QueryDocumentInfo {
  kind: 'upload' | 'case'
  id: string
  title: string
  page_count: number | null
  passages_total: number
  passages_used: number
  provisions: string[]
}

export interface SimilarCasesResponse {
  query: QueryDocumentInfo
  total_cases: number
  results: SimilarCase[]
  notices: string[]
  relevance_note: string
}

export interface AuditEvent {
  id: number
  occurred_at: string
  username: string | null
  action: string
  outcome: string
  target_type: string | null
  target_id: string | null
  details: Record<string, unknown>
  client_ip: string | null
}

export interface AuditPage {
  total: number
  events: AuditEvent[]
}

export interface ChatTurn {
  role: 'user' | 'assistant'
  content: string
}

export interface ChatSource {
  id: string
  kind: 'record' | 'passage'
  case_display_id: string
  case_title: string | null
  document_id: string | null
  page_start: number | null
  page_end: number | null
  excerpt: string
  cited: boolean
}

export interface ChatAnswer {
  answer: string
  answered: boolean
  sources: ChatSource[]
  notices: string[]
  model: string
  seconds: number
  disclaimer: string
}
