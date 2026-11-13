// Small helpers for imported findings (CM-6).

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

export const ITEM_COLORS: Record<string, string> = {
  log_event: 'blue',
  alert: 'red',
  cdr_result: 'grape',
  ipdr_result: 'violet',
  osint: 'teal',
  indicator: 'orange',
  report: 'cyan',
}

export const itemColor = (type?: string | null) => (type && ITEM_COLORS[type]) || 'gray'

/** A time as the source gave it, in its own timezone: "4 Mar 2026, 10:41 (UTC+05:30)". */
export function observedText(iso?: string | null): string {
  if (!iso) return ''
  const m = iso.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::\d{2}(?:\.\d+)?)?(Z|[+-]\d{2}:\d{2})$/)
  if (!m) return iso
  const [, year, month, day, hour, minute, zone] = m
  return `${Number(day)} ${MONTHS[Number(month) - 1]} ${year}, ${hour}:${minute} (UTC${zone === 'Z' ? '' : zone})`
}

/** "from … to …" for a period, or the single time. */
export function periodText(start?: string | null, end?: string | null): string {
  if (!start) return ''
  if (!end) return observedText(start)
  const a = observedText(start)
  const b = observedText(end)
  const sameDay = start.slice(0, 10) === end.slice(0, 10)
  return sameDay ? `${a.split(' (')[0]} to ${b.split(', ')[1]}` : `${a} to ${b}`
}

/** A suggested reason for linking two cases that share an identifier: the person checks and edits it. */
export function linkReason(label: string, value: string, here: string[], there: string[]): string {
  const ours = here.length ? ` (${here.join(', ')} here` : ''
  const theirs = there.length ? `${ours ? '; ' : ' ('}${there.join(', ')} there)` : ours ? ')' : ''
  return `The same ${label.toLowerCase()} ${value} appears in imported findings of both cases${ours}${theirs}.`
}
