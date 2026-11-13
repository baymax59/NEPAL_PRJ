// Words and colours for the values the backend uses. Unknown values are shown as they are, never guessed.

import type { NotificationOut } from './types'

export function humanize(value: string | null | undefined): string {
  if (!value) return ''
  const text = value.replaceAll('_', ' ').replaceAll('-', ' ')
  return text.charAt(0).toUpperCase() + text.slice(1)
}

interface Look {
  label: string
  color: string
}

const look = (table: Record<string, Look>, value: string | null | undefined): Look =>
  (value && table[value]) || { label: humanize(value), color: 'gray' }

const WORKFLOW: Record<string, Look> = {
  registered: { label: 'Registered', color: 'gray' },
  open: { label: 'Open', color: 'blue' },
  under_investigation: { label: 'Under investigation', color: 'hawk' },
  pending_evidence: { label: 'Pending evidence', color: 'yellow' },
  pending_review: { label: 'Pending review', color: 'orange' },
  approved_for_reporting: { label: 'Approved for reporting', color: 'teal' },
  investigation_completed: { label: 'Investigation completed', color: 'green' },
  closed: { label: 'Closed', color: 'dark' },
  archived: { label: 'Archived', color: 'gray' },
  reopened: { label: 'Reopened', color: 'grape' },
}
export const WORKFLOW_STATUSES = Object.keys(WORKFLOW)
export const workflowLook = (v?: string | null) => look(WORKFLOW, v)

const PRIORITY: Record<string, Look> = {
  low: { label: 'Low', color: 'gray' },
  medium: { label: 'Medium', color: 'blue' },
  high: { label: 'High', color: 'orange' },
  critical: { label: 'Critical', color: 'red' },
}
export const priorityLook = (v?: string | null) => look(PRIORITY, v)

const CLASSIFICATION: Record<string, Look> = {
  public: { label: 'Public', color: 'gray' },
  internal: { label: 'Internal', color: 'blue' },
  restricted: { label: 'Restricted', color: 'orange' },
  confidential: { label: 'Confidential', color: 'red' },
}
export const CLASSIFICATIONS = Object.keys(CLASSIFICATION)
export const classificationLook = (v?: string | null) => look(CLASSIFICATION, v)

const TASK_STATUS: Record<string, Look> = {
  open: { label: 'Open', color: 'blue' },
  in_progress: { label: 'In progress', color: 'hawk' },
  done: { label: 'Done', color: 'green' },
  cancelled: { label: 'Cancelled', color: 'gray' },
}
export const taskStatusLook = (v?: string | null) => look(TASK_STATUS, v)

const INTEGRITY: Record<string, Look> = {
  match: { label: 'File is original', color: 'green' },
  mismatch: { label: 'File was changed', color: 'red' },
  missing: { label: 'File missing', color: 'red' },
  never_checked: { label: 'Not checked yet', color: 'yellow' },
}
export const integrityLook = (v?: string | null) => look(INTEGRITY, v ?? 'never_checked')

const ROLE: Record<string, string> = {
  lead: 'Investigator (case lead)',
  contributor: 'Sub Investigator',
  analyst: 'Analyst',
  viewer: 'Viewer',
  super_admin: 'Super Admin',
  administrator: 'Administrator',
  supervisor: 'Supervisor',
  investigator: 'Investigator',
  sub_investigator: 'Sub Investigator',
}
export const roleLabel = (v?: string | null) => (v && ROLE[v]) || humanize(v)

const ENTRY: Record<string, Look> = {
  case_registered: { label: 'Case registered', color: 'violet' },
  folder_added: { label: 'Folder added', color: 'gray' },
  note_added: { label: 'Note added', color: 'green' },
  note_revised: { label: 'New version', color: 'blue' },
  evidence_added: { label: 'Exhibit added', color: 'teal' },
  file_withdrawn: { label: 'Withdrawn', color: 'orange' },
  file_sealed: { label: 'Sealed', color: 'red' },
  file_unsealed: { label: 'Unsealed', color: 'gray' },
  status_changed: { label: 'Status', color: 'hawk' },
  reference_added: { label: 'Official reference', color: 'indigo' },
  member_added: { label: 'Joined the team', color: 'green' },
  member_removed: { label: 'Left the team', color: 'orange' },
  lead_changed: { label: 'Case handed over', color: 'violet' },
  case_renumbered: { label: 'Case number', color: 'hawk' },
  link_added: { label: 'Case linked', color: 'grape' },
  import_added: { label: 'Imported finding', color: 'cyan' },
  timeline_generated: { label: 'Timeline', color: 'cyan' },
  report_generated: { label: 'Report', color: 'cyan' },
}
export const entryLook = (v?: string | null) => look(ENTRY, v)

export const ARTIFACT_TYPES: Record<string, string> = {
  note: 'Note',
  analysis: 'Analysis',
  transcription: 'Transcription',
  timeline: 'Timeline',
  case_summary: 'Case summary',
  official_references: 'Official references',
  report: 'Report',
  import: 'Imported finding',
  link: 'Case link',
}

const CUSTODY: Record<string, string> = {
  collected: 'Collected',
  ingested: 'Received into the evidence store',
  transferred: 'Handed over',
  acknowledged: 'Receipt acknowledged',
  declined: 'Handover declined',
  accessed: 'Accessed',
  verified: 'Integrity verified',
  sealed: 'Sealed',
  unsealed: 'Unsealed',
  exported: 'Exported',
}
export const custodyLabel = (v: string) => CUSTODY[v] ?? humanize(v)

/** A notice in one line, and where it leads. */
export function describeNotice(n: NotificationOut): { text: string; href: string | null } {
  const p = n.payload as Record<string, unknown>
  const by = typeof p.by === 'string' ? p.by : 'Someone'
  const task = p.task as { id?: string; display_id?: string; title?: string } | undefined
  const evidence = p.evidence as { id?: string; display_id?: string } | undefined
  const where = typeof p.case === 'string' ? p.case : ''
  const caseHref = typeof p.case_id === 'string' ? `/kh/case/${p.case_id}` : null
  const tab = (name: string) => (caseHref ? `${caseHref}/${name}` : null)
  switch (n.kind) {
    case 'case.assigned':
      return { text: `${by} made you the Investigator of ${where}${p.title ? ` “${String(p.title)}”` : ''}`, href: caseHref }
    case 'team.added':
      return { text: `${by} added you to ${where} as ${roleLabel(String(p.role ?? ''))}`, href: caseHref }
    case 'team.removed':
      return { text: `${by} took you off ${where}`, href: null }
    case 'team.role_changed':
      return { text: `${by} handed ${where} to another Investigator: you stay as ${roleLabel(String(p.role ?? ''))}`, href: caseHref }
    case 'task.assigned':
      return { text: `${by} assigned you ${task?.display_id ?? 'a task'}: ${task?.title ?? ''}`, href: caseHref }
    case 'task.status_changed':
      return { text: `${by} marked ${task?.display_id ?? 'a task'} as ${taskStatusLook(String(p.status ?? '')).label.toLowerCase()}`, href: caseHref }
    case 'chat.message':
      return { text: `${by} wrote ${p.group ? 'to the team' : 'to you'} in ${where}: “${String(p.preview ?? '')}”`, href: caseHref ? `${caseHref}/chat${p.group ? '' : `?with=${String(p.thread ?? '')}`}` : null }
    case 'account.self_registered':
      return { text: `${String(p.name ?? by)} (officer ${String(p.officer ?? '')}, ${String(p.station ?? '')}) created their own login: view-only until you raise their role and clearance`, href: '/kh/people' }
    case 'comment.added': {
      const on = p.on as { display_id?: string } | undefined
      return { text: `${by} commented on ${on?.display_id ?? 'your work'} (${where})`, href: caseHref }
    }
    case 'import.added': {
      const artifact = p.artifact as { display_id?: string } | undefined
      return {
        text: `${by} added ${artifact?.display_id ?? 'a finding'} (${String(p.item_type ?? 'imported finding').toLowerCase()} from ${String(p.source ?? 'a connected system')}) to ${where}`,
        href: tab('imports'),
      }
    }
    case 'legal_hold.placed':
      return { text: `${by} placed a legal hold on ${where}: it can't be archived until the hold is released`, href: caseHref }
    case 'legal_hold.released':
      return { text: `${by} released a legal hold on ${where}`, href: caseHref }
    case 'retention.decided':
      return { text: `${by} ${String(p.decision ?? 'decided')} the retention decision (${String(p.action ?? '')}) about ${where}`, href: caseHref }
    case 'governance.audit_chain_broken':
      return { text: `The audit chain check found ${String(p.problems ?? 'a')} problem(s), from event ${String(p.first_event ?? '?')}: look now`, href: '/audit' }
    case 'governance.evidence_integrity':
      return { text: `The evidence check found ${String(p.changed ?? 0)} changed and ${String(p.missing ?? 0)} missing file(s)`, href: '/kh/admin/evidence' }
    case 'custody.transfer_pending':
      return { text: `${by} is handing ${evidence?.display_id ?? 'an exhibit'} over to you: acknowledge receipt`, href: evidence?.id ? `/kh/evidence/${evidence.id}` : null }
    default:
      return { text: `${humanize(n.kind)}${where ? ` (${where})` : ''}`, href: caseHref }
  }
}

/** Allowed changes of a case's workflow status (the backend enforces the same table; spec §16). */
export const WORKFLOW_NEXT: Record<string, string[]> = {
  registered: ['open', 'under_investigation'],
  open: ['under_investigation', 'closed'],
  under_investigation: ['pending_evidence', 'pending_review', 'investigation_completed'],
  pending_evidence: ['under_investigation'],
  pending_review: ['under_investigation', 'approved_for_reporting'],
  approved_for_reporting: ['under_investigation', 'investigation_completed'],
  investigation_completed: ['under_investigation', 'closed'],
  closed: ['archived', 'reopened'],
  archived: ['reopened'],
  reopened: ['under_investigation'],
}
/** Workflow statuses only the supervisor or an administrator may set. */
export const SUPERVISOR_DECISIONS = ['closed', 'archived', 'reopened']
