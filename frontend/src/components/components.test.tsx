import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { SearchHit } from '../api/types'
import { renderWithProviders } from '../test/render'
import { SearchResultCard } from './CaseCards'
import { SnippetText } from './SnippetText'

describe('SnippetText', () => {
  it('highlights the matched words', () => {
    const { container } = renderWithProviders(
      <SnippetText
        parts={[
          { text: 'Anticipatory bail', match: true },
          { text: ' was refused.', match: false },
        ]}
      />,
    )
    expect(container.querySelector('mark')).toHaveTextContent('Anticipatory bail')
    expect(container).toHaveTextContent('Anticipatory bail was refused.')
  })

  it('shows markup from a document as text and never runs it', () => {
    const { container } = renderWithProviders(
      <SnippetText parts={[{ text: '<script>alert(1)</script><b>bold</b>', match: false }]} />,
    )
    expect(container.querySelector('script')).toBeNull()
    expect(container.querySelector('b')).toBeNull()
    expect(container).toHaveTextContent('<script>alert(1)</script><b>bold</b>')
  })
})

const HIT: SearchHit = {
  case: {
    display_id: 'SC-TEST-1',
    title: 'A versus B',
    category: null,
    court_or_agency: 'Supreme Court of India',
    status: null,
    outcome: null,
    primary_date: '2023-01-12',
    primary_date_kind: 'decision',
    source_system: 'sc_judgments',
    reference_numbers: { neutral_citation: '2023 INSC 23' },
    sensitivity: 'public',
    processing_status: 'indexed',
    missing_fields: ['category', 'status', 'outcome'],
  },
  relevance: 87,
  match_type: 'keyword+semantic',
  keyword_rank: 0.5,
  semantic_similarity: 0.81,
  matching_passages: 2,
  reasons: ['Cites Section 302 IPC, as in your search', 'Words not found: eyewitness'],
  passages: [
    {
      chunk_id: 1,
      document_id: 'doc',
      page_start: 18,
      page_end: 19,
      snippet: [{ text: 'circumstantial evidence', match: true }],
      matched_by: ['keyword', 'semantic'],
      similarity: 0.81,
    },
  ],
}

describe('SearchResultCard', () => {
  it('shows what the source records and marks what it does not', () => {
    renderWithProviders(<SearchResultCard hit={HIT} query="murder" note="Relevance orders results." />)

    expect(screen.getByRole('link', { name: 'A versus B' })).toHaveAttribute('href', '/cases/SC-TEST-1')
    expect(screen.getByText('no outcome recorded in the source')).toBeInTheDocument()
    expect(screen.getByText('Not in the source record: category, status, outcome')).toBeInTheDocument()
    expect(screen.getByText('2023 INSC 23')).toBeInTheDocument()
    expect(screen.getByLabelText('Relevance 87 out of 100')).toBeInTheDocument()
    expect(screen.getByText('Cites Section 302 IPC, as in your search')).toBeInTheDocument()
    expect(screen.getByText(/pp\. 18–19 · matched by keyword and semantic/)).toBeInTheDocument()
  })
})
