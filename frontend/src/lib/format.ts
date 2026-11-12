// Display helpers. Missing values are always shown as missing, never guessed.

export const NOT_IN_SOURCE = 'Not available in source'

const dateFormat = new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
const dateTimeFormat = new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium', timeStyle: 'medium' })

export function formatDate(iso: string | null | undefined): string | null {
  if (!iso) return null
  const date = new Date(iso.length === 10 ? `${iso}T00:00:00` : iso)
  return Number.isNaN(date.getTime()) ? iso : dateFormat.format(date)
}

export function formatDateTime(iso: string): string {
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? iso : dateTimeFormat.format(date)
}

export function pageLabel(start: number | null, end: number | null): string {
  if (start === null) return 'no page numbers'
  return start === end || end === null ? `p. ${start}` : `pp. ${start}–${end}`
}

const FIELD_NAMES: Record<string, string> = {
  title: 'title',
  category: 'category',
  court_or_agency: 'court',
  status: 'status',
  summary: 'summary',
  outcome: 'outcome',
  dates: 'dates',
  parties: 'parties',
  documents: 'documents',
}

export function fieldName(field: string): string {
  return FIELD_NAMES[field] ?? field.replaceAll('_', ' ')
}

export function sentenceCase(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1).replaceAll('_', ' ')
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
