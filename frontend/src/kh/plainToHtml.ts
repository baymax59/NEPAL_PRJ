/** Plain text as the editor first shows it when a case has no styled copy: each line becomes a paragraph. */
export function plainToHtml(plain: string): string {
  const escape = (t: string) => t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  return plain
    .split('\n')
    .map((line) => `<p>${escape(line)}</p>`)
    .join('')
}
