// Small helpers of the Case Intelligence tab (kept apart from components for fast refresh).

export function pageText(start?: number | null, end?: number | null): string {
  if (start == null) return ''
  return start === end || end == null ? `p.${start}` : `pp.${start}–${end}`
}

export type SourceLike = { kind: string; item_id?: string | null; path?: string | null; display_id: string; version_number?: number | null }

/** Where to read the source: an exhibit's page, or a note opened in the case's Files tab. */
export function sourceHref(caseId: string, source: SourceLike): string | undefined {
  if (source.kind === 'evidence' && source.item_id) return `/kh/evidence/${source.item_id}`
  if (source.kind === 'artifact' && source.item_id) return `/kh/case/${caseId}/files?open=${encodeURIComponent(source.item_id)}`
  return undefined
}

const KIND_LABEL: Record<string, string> = {
  evidence: 'Exhibit',
  case_summary: 'Case summary',
  official_references: 'Official references',
  note: 'Note',
  analysis: 'Analysis',
  transcription: 'Transcription',
  timeline: 'Timeline',
  link: 'Case link',
  report: 'Report',
  import: 'Import',
}

export function kindLabel(kind: string, artifactType?: string | null): string {
  return kind === 'evidence' ? KIND_LABEL.evidence : (KIND_LABEL[artifactType ?? ''] ?? 'Note')
}
