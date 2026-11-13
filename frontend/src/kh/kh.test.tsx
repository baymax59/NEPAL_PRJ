// Component and helper tests for the Knight Hawk screens. All data is fictional.

import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '../test/render'
import { folderNameProblem, withOffset } from './case/helpers'
import { ContentView, DiffView } from './content'
import { diffLines } from './diff'
import { describeNotice, entryLook, roleLabel, WORKFLOW_NEXT, WORKFLOW_STATUSES } from './labels'
import { keysFor, parseEvent, watchFor } from './live'
import { timeAgo } from './time'
import type { NotificationOut } from './types'
import { ConfirmModal, EntryBadge, EntryNumber, IntegrityBadge } from './ui'

describe('diffLines', () => {
  it('marks kept, removed and added lines', () => {
    const lines = diffLines('a\nb\nc', 'a\nc\nd')
    expect(lines.map((l) => `${l.kind}:${l.text}`)).toEqual(['same:a', 'removed:b', 'same:c', 'added:d'])
  })

  it('treats a first version as all added', () => {
    expect(diffLines('', 'one\ntwo').every((l) => l.kind === 'added')).toBe(true)
  })
})

describe('the live notice stream', () => {
  it('reads one Server-Sent Events block', () => {
    expect(parseEvent('event: notices\ndata: {"unread": 2, "latest": 7}')).toEqual({ event: 'notices', data: '{"unread": 2, "latest": 7}' })
    expect(parseEvent(': still here')).toEqual({ event: 'message', data: '' })
    expect(parseEvent('event: activity\ndata: {"scope": "admin", "marker": "0123456789abcdef"}').event).toBe('activity')
  })

  it('knows which page is open, so the server can say when what it shows has changed', () => {
    const id = '0f8fad5b-d9cb-469f-a165-70867728950e'
    expect(watchFor(`/kh/case/${id}`)).toBe(`case:${id}`)
    expect(watchFor(`/kh/case/${id.toUpperCase()}/files`)).toBe(`case:${id}`)
    expect(watchFor(`/kh/case/${id}/history`)).toBe(`case:${id}`)
    expect(watchFor(`/kh/evidence/${id}`)).toBe(`evidence:${id}`)
    expect(watchFor('/kh/admin')).toBe('admin')
    expect(watchFor(`/kh/admin/cases/${id}`)).toBe('admin')
    // Pages without one case (the dashboard, inboxes) follow notices only; a malformed address follows nothing. The old
    // repository and review pages no longer exist.
    expect(watchFor('/kh')).toBeNull()
    expect(watchFor('/kh/tasks')).toBeNull()
    expect(watchFor(`/kh/repo/${id}`)).toBeNull()
    expect(watchFor(`/kh/review/${id}`)).toBeNull()
    expect(watchFor('/kh/case/not-an-id')).toBeNull()
    expect(watchFor('/kh/administrator')).toBeNull()
  })

  it('refreshes only the data of the page that changed', () => {
    expect(keysFor('admin')).toEqual([['kh', 'admin'], ['kh', 'cases']])
    const caseKeys = keysFor('case:0f8fad5b-d9cb-469f-a165-70867728950e')
    expect(caseKeys).toContainEqual(['kh', 'case'])
    expect(caseKeys).not.toContainEqual(['kh', 'notifications']) // notices have their own event
  })
})

describe('notices', () => {
  const CASE = '0f8fad5b-d9cb-469f-a165-70867728950e'
  const notice = (kind: string, payload: Record<string, unknown>): NotificationOut => ({ id: 1, kind, payload, created_at: '2026-11-07T10:00:00Z', read_at: null })

  it('say who added you to a case, in which part, and lead to the case', () => {
    const { text, href } = describeNotice(notice('team.added', { by: 'SI Arun (fictional)', case: 'KH-2026-0001', case_id: CASE, role: 'analyst' }))
    expect(text).toBe('SI Arun (fictional) added you to KH-2026-0001 as Analyst')
    expect(href).toBe(`/kh/case/${CASE}`)
  })

  it('say who made you the Investigator of a case, and who took you off one', () => {
    expect(describeNotice(notice('case.assigned', { by: 'Supervisor (fictional)', case: 'KH-2026-0001', case_id: CASE, title: 'Phishing' })).text).toContain('made you the Investigator of KH-2026-0001')
    expect(describeNotice(notice('team.removed', { by: 'SI Arun (fictional)', case: 'KH-2026-0001', case_id: CASE })).href).toBeNull()
  })

  it('lead a notice about an earlier task to the case itself: there is no task board any more', () => {
    const { text, href } = describeNotice(notice('task.assigned', { by: 'SI Arun (fictional)', case: 'KH-2026-0001', case_id: CASE, task: { id: 't1', display_id: 'TASK-0001', title: 'Ask the bank' } }))
    expect(text).toBe('SI Arun (fictional) assigned you TASK-0001: Ask the bank')
    expect(href).toBe(`/kh/case/${CASE}`)
  })

  it('lead a custody handover to the exhibit', () => {
    expect(describeNotice(notice('custody.transfer_pending', { by: 'X', evidence: { id: 'e1', display_id: 'EV-0001' } })).href).toBe('/kh/evidence/e1')
  })

  it('show unknown kinds as they are, never guessed', () => {
    expect(describeNotice(notice('something.new', { case: 'KH-2026-0001' })).text).toBe('Something.new (KH-2026-0001)')
  })
})

describe('helpers', () => {
  it('accept the folder names the backend accepts, and say what is wrong with the others', () => {
    expect(folderNameProblem('')).toBeNull()
    expect(folderNameProblem('bank-letters')).toBeNull()
    expect(folderNameProblem('CDR analysis 2026.v2')).toBeNull()
    expect(folderNameProblem('-secret')).toMatch(/starting with a letter or digit/)
    expect(folderNameProblem('a/b')).toMatch(/Use letters, digits/)
    expect(folderNameProblem('x'.repeat(101))).toMatch(/At most 100/)
  })

  it('add the computer’s UTC offset to a local time', () => {
    expect(withOffset('')).toBeNull()
    expect(withOffset('2026-11-02T14:30')).toMatch(/^2026-11-02T14:30:00[+-]\d{2}:\d{2}$/)
  })

  it('say how long ago something happened', () => {
    const now = Date.parse('2026-11-07T12:00:00Z')
    expect(timeAgo('2026-11-07T11:59:30Z', now)).toBe('just now')
    expect(timeAgo('2026-11-07T09:00:00Z', now)).toBe('3 hours ago')
  })

  it('allow only known workflow statuses as next steps', () => {
    for (const [from, next] of Object.entries(WORKFLOW_NEXT)) {
      expect(WORKFLOW_STATUSES).toContain(from)
      for (const to of next) expect(WORKFLOW_STATUSES).toContain(to)
    }
  })

  it('name the parts of a case in plain words', () => {
    expect(roleLabel('lead')).toBe('Investigator (case lead)')
    expect(roleLabel('sub_investigator')).toBe('Sub Investigator')
    expect(roleLabel('analyst')).toBe('Analyst')
    expect(roleLabel('viewer')).toBe('Viewer')
  })
})

describe('labels', () => {
  it('mark evidence that was never checked', () => {
    renderWithProviders(
      <>
        <IntegrityBadge result="match" />
        <IntegrityBadge result={null} />
      </>,
    )
    expect(screen.getByText('File is original')).toBeInTheDocument()
    expect(screen.getByText('Not checked yet')).toBeInTheDocument()
  })

  it('tell what a history entry records, in words and never as a code', () => {
    renderWithProviders(
      <>
        <EntryBadge value="note_revised" />
        <EntryBadge value="member_added" />
        <EntryBadge value="file_withdrawn" />
      </>,
    )
    expect(screen.getByText('New version')).toBeInTheDocument()
    expect(screen.getByText('Joined the team')).toBeInTheDocument()
    expect(screen.getByText('Withdrawn')).toBeInTheDocument()
    expect(entryLook('something_new').label).toBe('Something new') // unknown kinds are shown as they are
  })

  it('show an entry of the history as "Entry 14", linking to it, with no code', () => {
    renderWithProviders(<EntryNumber seq={14} caseId="c1" />)
    const link = screen.getByRole('link', { name: 'Entry 14' })
    expect(link).toHaveAttribute('href', '/kh/case/c1/history#entry-14')
    expect(link).toHaveTextContent('Entry 14')
  })
})

describe('ConfirmModal', () => {
  it('asks for a reason before a sensitive change', async () => {
    const user = userEvent.setup()
    const onConfirm = vi.fn()
    renderWithProviders(
      <ConfirmModal opened onClose={() => {}} title="Take off the team?" confirmLabel="Take off the team" reason="required" minReason={5} onConfirm={onConfirm}>
        Their work stays credited to them.
      </ConfirmModal>,
    )
    const confirm = screen.getByRole('button', { name: 'Take off the team' })
    expect(confirm).toBeDisabled()
    await user.type(screen.getByRole('textbox'), '  No longer on the case  ')
    expect(confirm).toBeEnabled()
    await user.click(confirm)
    expect(onConfirm).toHaveBeenCalledWith('No longer on the case')
  })
})

describe('content', () => {
  it('shows a note as text and a structured record as rows', () => {
    renderWithProviders(
      <>
        <ContentView content={{ text: 'Three transfers (fictional)' }} />
        <ContentView content={{ case_type: 'cyber_fraud', priority: 'high' }} />
      </>,
    )
    expect(screen.getByText('Three transfers (fictional)')).toBeInTheDocument()
    expect(screen.getByText('Case type')).toBeInTheDocument()
    expect(screen.getByText('cyber_fraud')).toBeInTheDocument()
  })

  it('counts the lines added and removed between two versions', () => {
    renderWithProviders(<DiffView before={{ text: 'a\nb' }} after={{ text: 'a\nc\nd' }} />)
    expect(screen.getByText('+2')).toBeInTheDocument()
    expect(screen.getByText('−1')).toBeInTheDocument()
  })
})
