import { MantineProvider } from '@mantine/core'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeAll, describe, expect, it, vi } from 'vitest'
import { plainToHtml } from './plainToHtml'
import { RichTextEditor, RichTextView } from './RichText'

const wrap = (node: React.ReactNode) => render(<MantineProvider>{node}</MantineProvider>)

// jsdom (the test browser) has no page layout: the editor asks where the cursor is on the page when it scrolls, so say "nowhere".
beforeAll(() => {
  const none = { length: 0, item: () => null, [Symbol.iterator]: function* () {} } as unknown as DOMRectList
  Range.prototype.getClientRects = () => none
  Range.prototype.getBoundingClientRect = () => new DOMRect()
})

describe('RichTextView', () => {
  it('shows the formatting that was written', () => {
    const { container } = wrap(<RichTextView html={'<p style="text-align: center"><strong>Bold</strong> <em>slanted</em> <u>under</u></p><ol><li><p>one</p></li></ol>'} />)
    expect(container.querySelector('strong')?.textContent).toBe('Bold')
    expect(container.querySelector('em')).not.toBeNull()
    expect(container.querySelector('u')).not.toBeNull()
    expect(container.querySelector('ol li')?.textContent).toBe('one')
    expect(container.querySelector('p')?.getAttribute('style')).toContain('text-align: center')
  })

  it('shows nothing that could run: scripts, handlers, images, links', () => {
    const { container } = wrap(
      <RichTextView html={'<p onclick="steal()">Text</p><script>steal()</script><img src=x onerror="steal()"><a href="javascript:steal()">link</a><iframe src="https://example.com"></iframe>'} />,
    )
    expect(container.innerHTML).not.toMatch(/script|onclick|onerror|javascript|<img|<iframe|<a /i)
    expect(container.textContent).toContain('Text')
  })
})

describe('plainToHtml', () => {
  it('makes a paragraph of each line and escapes the text', () => {
    expect(plainToHtml('first\nsecond <b>')).toBe('<p>first</p><p>second &lt;b&gt;</p>')
  })
})

describe('RichTextEditor', () => {
  it('offers the formatting toolbar and tells what was written, as styled text and as plain text', async () => {
    const onChange = vi.fn()
    wrap(<RichTextEditor initial={plainToHtml('A complainant reports three transfers.')} onChange={onChange} />)
    for (const name of ['Undo', 'Redo', 'Font', 'Text size', 'Bold', 'Italic', 'Underline', 'Text colour', 'Alignment', 'Numbered list', 'More formatting options']) {
      expect(await screen.findByRole('button', { name })).toBeTruthy()
    }
    expect(screen.getByRole('toolbar', { name: 'Text formatting' })).toBeTruthy()
    const box = screen.getByRole('textbox', { name: 'Description' })
    expect(box.textContent).toBe('A complainant reports three transfers.')

    await userEvent.click(screen.getByRole('button', { name: 'Bold' }))
    await userEvent.keyboard('Urgent ')
    await waitFor(() => expect(onChange).toHaveBeenCalled())
    const [html, text] = onChange.mock.calls.at(-1) as [string, string]
    expect(html).toContain('<strong>')
    expect(text).toContain('Urgent')
    expect(text).not.toContain('<')
  })
})
