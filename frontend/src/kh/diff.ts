// The text of an entry's content, and line-by-line differences between two versions.

type Content = Record<string, unknown> | null | undefined

/** The text of a note ({"text": "..."}), or the content written out as readable lines. */
export function contentText(content: Content): string {
  if (!content) return ''
  if (typeof content.text === 'string' && Object.keys(content).length === 1) return content.text
  return JSON.stringify(content, null, 2)
}

export interface DiffLine {
  kind: 'same' | 'added' | 'removed'
  text: string
  before?: number
  after?: number
}

/** A line-by-line difference (longest common subsequence). Large texts fall back to "all removed, all added". */
export function diffLines(before: string, after: string): DiffLine[] {
  const a = before ? before.split('\n') : []
  const b = after ? after.split('\n') : []
  if (a.length * b.length > 4_000_000) {
    return [...a.map((text, i) => ({ kind: 'removed' as const, text, before: i + 1 })), ...b.map((text, i) => ({ kind: 'added' as const, text, after: i + 1 }))]
  }
  const lcs: number[][] = Array.from({ length: a.length + 1 }, () => new Array<number>(b.length + 1).fill(0))
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      lcs[i][j] = a[i] === b[j] ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1])
    }
  }
  const lines: DiffLine[] = []
  let i = 0
  let j = 0
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      lines.push({ kind: 'same', text: a[i], before: i + 1, after: j + 1 })
      i++
      j++
    } else if (lcs[i + 1][j] >= lcs[i][j + 1]) {
      lines.push({ kind: 'removed', text: a[i], before: i + 1 })
      i++
    } else {
      lines.push({ kind: 'added', text: b[j], after: j + 1 })
      j++
    }
  }
  while (i < a.length) lines.push({ kind: 'removed', text: a[i], before: ++i })
  while (j < b.length) lines.push({ kind: 'added', text: b[j], after: ++j })
  return lines
}
