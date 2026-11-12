import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { ChatAnswer, ChatSource } from '../api/types'
import { renderWithProviders } from '../test/render'
import { historyFor, type Exchange } from '../lib/chat'
import { ExchangeView } from './CaseAssistant'

const SOURCE: ChatSource = {
  id: 'S2',
  kind: 'passage',
  case_display_id: 'SC-TEST-1',
  case_title: 'A versus B',
  document_id: 'doc-1',
  page_start: 4,
  page_end: 5,
  excerpt: 'The recovery of the weapon was not proved.',
  cited: true,
}

function exchange(answer: Partial<ChatAnswer>, question = 'Why was the appeal allowed?'): Exchange {
  return {
    question,
    compareWith: null,
    answer: {
      answer: 'The recovery was not proved [S2].',
      answered: true,
      sources: [SOURCE],
      notices: [],
      model: 'test-model',
      seconds: 90,
      disclaimer: 'It can make mistakes.',
      ...answer,
    },
  }
}

describe('ExchangeView', () => {
  it('shows citations as source markers and lists the sources', () => {
    const { container } = renderWithProviders(<ExchangeView exchange={exchange({})} />)
    expect(container).toHaveTextContent('The recovery was not proved S2.')
    expect(container).not.toHaveTextContent('[S2]')
    expect(screen.getByText('Sources given to the assistant (1, 1 cited)')).toBeInTheDocument()
    expect(screen.queryByText('Not in the records')).toBeNull()
  })

  it('marks answers the records do not contain, and shows notices', () => {
    renderWithProviders(
      <ExchangeView
        exchange={exchange({
          answer: 'The case records provided do not contain this information.',
          answered: false,
          notices: ['This answer cites none of the sources.'],
        })}
      />,
    )
    expect(screen.getByText('Not in the records')).toBeInTheDocument()
    expect(screen.getByText('This answer cites none of the sources.')).toBeInTheDocument()
  })

  it('shows markup in an answer as text and never runs it', () => {
    const { container } = renderWithProviders(
      <ExchangeView exchange={exchange({ answer: '<img src=x onerror=alert(1)> [S2]' })} />,
    )
    expect(container.querySelector('img')).toBeNull()
    expect(container).toHaveTextContent('<img src=x onerror=alert(1)>')
  })
})

describe('historyFor', () => {
  it('sends only the previous question and answer', () => {
    const turns = historyFor([exchange({}, 'one'), exchange({}, 'two'), exchange({}, 'three')])
    expect(turns).toEqual([
      { role: 'user', content: 'three' },
      { role: 'assistant', content: 'The recovery was not proved [S2].' },
    ])
  })
})
