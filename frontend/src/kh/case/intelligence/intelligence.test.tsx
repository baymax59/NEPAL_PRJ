// Case Intelligence tab: helpers and components. All data is fictional.

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '../../../test/render'
import { kh } from '../../api'
import type { CaseAnswer, CaseDetail, Coverage, TimelineView as TimelineData } from '../../types'
import { AssistantView } from './AssistantView'
import { CoverageBar, Relevance } from './common'
import { kindLabel, pageText, sourceHref } from './format'
import { TimelineView } from './TimelineView'

vi.mock('../../api', () => ({ kh: { timeline: vi.fn(), askCase: vi.fn(), rebuildTimeline: vi.fn() }, newKey: () => 'key' }))

const DETAIL = {
  id: 'case-1',
  display_id: 'KH-2026-0009',
  can: { add_files: true },
} as unknown as CaseDetail

function withQuery(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return renderWithProviders(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

const coverage = (overrides: Partial<Coverage> = {}): Coverage => ({
  documents: 3,
  readable: 2,
  indexed: 1,
  pending: ['EV-0002'],
  no_text: [],
  unreadable: [],
  not_readable: [{ display_id: 'EV-0003', reason: 'no text to read in a image file' }],
  notes: 2,
  notes_indexed: 2,
  passages: 12,
  passages_without_meaning: 0,
  embedding_model: 'test-model',
  complete: false,
  ...overrides,
})

describe('helpers', () => {
  it('cite pages as people write them', () => {
    expect(pageText(3, 3)).toBe('p.3')
    expect(pageText(3, 5)).toBe('pp.3–5')
    expect(pageText(null, null)).toBe('')
  })

  it('lead an exhibit to its page and a note to the case’s Files tab', () => {
    expect(sourceHref('c1', { kind: 'evidence', item_id: 'e1', display_id: 'EV-0001' })).toBe('/kh/evidence/e1')
    expect(sourceHref('c1', { kind: 'artifact', item_id: 'n1', display_id: 'NOTE-0001' })).toBe('/kh/case/c1/files?open=n1')
    expect(sourceHref('c1', { kind: 'case_record', display_id: 'KH-2026-0009' })).toBeUndefined()
    expect(kindLabel('artifact', 'case_summary')).toBe('Case summary')
  })
})

describe('CoverageBar', () => {
  it('says what was read and offers to read the rest', async () => {
    const prepare = vi.fn()
    renderWithProviders(<CoverageBar coverage={coverage()} onPrepare={prepare} preparing={false} />)
    expect(screen.getByText('1 waiting to be read')).toBeInTheDocument()
    expect(screen.getByText('1 not read')).toBeInTheDocument()
    expect(screen.getByText(/sealed exhibits and anything above your clearance never reach results/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Read now' }))
    expect(prepare).toHaveBeenCalledOnce()
  })

  it('offers nothing more once everything is read', () => {
    renderWithProviders(<CoverageBar coverage={coverage({ pending: [], indexed: 2, complete: true })} onPrepare={() => {}} preparing={false} />)
    expect(screen.queryByRole('button', { name: 'Read now' })).toBeNull()
  })

  it('shows relevance as a labelled meter', () => {
    renderWithProviders(<Relevance value={73} />)
    expect(screen.getByRole('progressbar', { name: 'Relevance 73 out of 100' })).toBeInTheDocument()
  })
})

describe('TimelineView', () => {
  beforeEach(() => vi.mocked(kh.timeline).mockReset())

  it('shows each dated entry with its exhibit and page', async () => {
    vi.mocked(kh.timeline).mockResolvedValue({
      timeline: {
        folder: 'timeline',
        artifact_id: 't1',
        display_id: 'TML-0001',
        version_number: 2,
        versions: 2,
        created_at: '2026-11-07T10:00:00Z',
        author: { id: 'u1', username: 'inv.arun', display_name: 'SI Arun (fictional)' },
        based_on_entry: 9,
        method: 'Built automatically (fictional test).',
        shared_view: 'Sealed exhibits are never used.',
        events: [
          {
            date: '2025-03-03',
            date_text: '3 March 2025',
            description: 'The complainant received a call (fictional).',
            kind: 'dated_mention',
            method: 'text',
            page: 2,
            source: { kind: 'evidence', display_id: 'EV-0001', title: 'FIR', path: 'complainant/fir.pdf', version_number: 1, version_id: 'v1', item_id: 'e1' },
          },
        ],
        sources_used: [{ kind: 'evidence', display_id: 'EV-0001', title: 'FIR', path: 'complainant/fir.pdf', version_number: 1, version_id: 'v1', item_id: 'e1', events: 1 }],
        not_used: [],
      },
    } as TimelineData)
    withQuery(<TimelineView detail={DETAIL} />)
    expect(await screen.findByText('The complainant received a call (fictional).')).toBeInTheDocument()
    expect(screen.getByText('TML-0001 · version 2 of 2')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'EV-0001 v1 · p.2' })).toHaveAttribute('href', '/kh/evidence/e1')
    expect(screen.getByRole('link', { name: 'Entry 9' })).toHaveAttribute('href', '/kh/case/case-1/history#entry-9')
    expect(screen.getByRole('button', { name: 'Rebuild the timeline' })).toBeInTheDocument()
  })

  it('explains what a timeline is when there is none yet', async () => {
    vi.mocked(kh.timeline).mockResolvedValue({ timeline: null } as TimelineData)
    withQuery(<TimelineView detail={DETAIL} />)
    expect(await screen.findByText('No timeline yet')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Build the timeline' })).toBeInTheDocument()
  })
})

describe('AssistantView', () => {
  it('shows the answer with markers naming exhibit, version and page', async () => {
    vi.mocked(kh.askCase).mockResolvedValue({
      answer: 'INR 85000 was sent on 4 March 2025 [S2].',
      answered: true,
      sources: [
        { id: 'S1', kind: 'case_record', display_id: 'KH-2026-0009', title: 'Case', path: null, version_number: null, page_start: null, page_end: null, excerpt: 'Recorded facts', item_id: null, cited: false },
        { id: 'S2', kind: 'evidence', display_id: 'EV-0001', title: 'Bank statement', path: 'financial/statement.pdf', version_number: 1, page_start: 1, page_end: 1, excerpt: 'INR 85000', item_id: 'e1', cited: true },
      ],
      notices: [],
      model: 'fake-model',
      seconds: 1.5,
      disclaimer: 'Answers can be wrong (fictional test).',
      coverage: coverage(),
    } as CaseAnswer)
    withQuery(<AssistantView detail={DETAIL} />)
    await userEvent.type(screen.getByLabelText('Your question'), 'What happened on 4 March 2025?')
    await userEvent.click(screen.getByRole('button', { name: 'Ask' }))
    expect(await screen.findByText(/INR 85000 was sent on 4 March 2025/)).toBeInTheDocument()
    expect(screen.getAllByText('S2').length).toBeGreaterThanOrEqual(1) // in the answer, and again in the sources list
    expect(vi.mocked(kh.askCase)).toHaveBeenCalledWith('case-1', { question: 'What happened on 4 March 2025?', history: [] })
    expect(screen.getByText('Sources given to the assistant (2, 1 cited)')).toBeInTheDocument()
  })
})
