// The plain case screens: Files, Team, History and Overview. All data is fictional. The server decides what each person may do
// (the `can` flags); these tests check that the screens offer exactly that, and send what the server expects.

import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthContext, type AuthValue } from '../../auth/context'
import type { UserOut } from '../../api/types'
import { renderWithProviders } from '../../test/render'
import { kh } from '../api'
import type { ArtifactHistory, CaseDetail, FilesView, HistoryCheck, HistoryView, TeamView } from '../types'
import { CaseContext } from './context'
import { CaseNumberDialog } from './dialogs'
import { FilesTab } from './FilesTab'
import { HistoryTab } from './HistoryTab'
import { OverviewTab } from './OverviewTab'
import { TeamTab } from './TeamTab'

vi.mock('../api', () => ({
  kh: {
    files: vi.fn(),
    artifactVersions: vi.fn(),
    withdrawNote: vi.fn(),
    team: vi.fn(),
    accessHistory: vi.fn(),
    removeMember: vi.fn(),
    history: vi.fn(),
    historyCheck: vi.fn(),
    caseGovernance: vi.fn(),
    caseTypes: vi.fn(),
    changeCaseNumber: vi.fn(),
  },
  newKey: () => 'key',
}))

const ARUN = { id: 'u-arun', username: 'inv.arun', display_name: 'SI Arun (fictional)' }
const MEERA = { id: 'u-meera', username: 'sub.meera', display_name: 'ASI Meera (fictional)' }

const detail = (can: Record<string, boolean>, over: Record<string, unknown> = {}) =>
  ({
    id: 'case-1',
    display_id: 'KH-2026-0009',
    title: 'Online fraud (fictional)',
    case_type: 'cyber_fraud',
    case_type_label: 'Cyber fraud',
    priority: 'high',
    classification: 'restricted',
    workflow_status: 'under_investigation',
    official_status: null,
    official_references: [],
    my_role: 'lead',
    description: 'Fictional: three transfers.',
    jurisdiction: null,
    supervisor: null,
    created_by: ARUN,
    created_at: '2026-11-07T10:00:00Z',
    lead: ARUN,
    references: [],
    status_history: [],
    folders: [
      { id: 'f1', name: 'case-information', system: false, files: 1, added_at: '2026-11-07T10:00:00Z' },
      { id: 'f2', name: 'bank-letters', system: false, files: 1, added_at: '2026-11-07T10:00:00Z' },
    ],
    team: [],
    can: { add_files: false, add_folders: false, withdraw: false, manage_team: false, hand_over: false, create_tasks: false, comment: false, change_workflow_status: false, ...can },
    ...over,
  }) as unknown as CaseDetail

const asUser: AuthValue = {
  user: { id: 'u-arun', username: 'inv.arun', display_name: 'SI Arun (fictional)', org_role: 'investigator' } as unknown as UserOut,
  loading: false,
  login: vi.fn(),
  loginSecondStep: vi.fn(),
  logout: vi.fn(),
  reload: vi.fn(),
  hasRole: () => true,
}

function page(ui: ReactNode, d: CaseDetail, route = '/kh/case/case-1/files') {
  return renderWithProviders(
    <AuthContext.Provider value={asUser}>
      <CaseContext value={d}>{ui}</CaseContext>
    </AuthContext.Provider>,
    route,
  )
}

const FILES = {
  case: {},
  folders: [],
  files: [
    { kind: 'note', id: 'n1', display_id: 'NOTE-0001', title: 'First steps (fictional)', folder: 'case-information', status: 'active', sealed: false, type: 'note', created_by: ARUN, created_at: '2026-11-07T10:00:00Z', updated_at: '2026-11-07T11:00:00Z', version_number: 2, withdrawn_reason: null, withdrawn_at: null },
    {
      kind: 'evidence', id: 'e1', display_id: 'EV-0001', title: 'Bank statement (fictional)', folder: 'bank-letters', status: 'active', sealed: true, type: 'bank_statement', created_by: ARUN,
      created_at: '2026-11-07T10:00:00Z', updated_at: '2026-11-07T10:00:00Z', version_number: null, withdrawn_reason: null, withdrawn_at: null,
      evidence: { mime_type: 'application/pdf', size_bytes: 2048 },
    },
  ],
} as unknown as FilesView

describe('FilesTab', () => {
  beforeEach(() => vi.mocked(kh.files).mockReset())

  it('lists the folders with their counts and the files, and offers to add only to those who may', async () => {
    vi.mocked(kh.files).mockResolvedValue(FILES)
    page(<FilesTab />, detail({ add_files: true, add_folders: true }))
    expect(await screen.findByText('First steps (fictional)')).toBeInTheDocument()
    expect(screen.getByText('NOTE-0001')).toBeInTheDocument()
    expect(screen.getByText('version 2')).toBeInTheDocument()
    expect(screen.getByText('Bank statement (fictional)')).toBeInTheDocument()
    expect(screen.getByText('application/pdf · 2 KB')).toBeInTheDocument()
    expect(screen.getByText('bank-letters', { selector: '.mantine-NavLink-label' })).toBeInTheDocument()
    for (const name of ['New folder', 'New note', 'Add exhibit']) expect(screen.getByRole('button', { name })).toBeInTheDocument()
    expect(screen.queryByText(/commit|branch|clone/i)).toBeNull()
  })

  it('shows a Viewer the files and no way to add', async () => {
    vi.mocked(kh.files).mockResolvedValue(FILES)
    page(<FilesTab />, detail({}, { my_role: 'viewer' }))
    expect(await screen.findByText('First steps (fictional)')).toBeInTheDocument()
    for (const name of ['New folder', 'New note', 'Add exhibit']) expect(screen.queryByRole('button', { name })).toBeNull()
  })

  it('shows only the chosen folder', async () => {
    vi.mocked(kh.files).mockResolvedValue(FILES)
    const user = userEvent.setup()
    page(<FilesTab />, detail({ add_files: true }))
    await screen.findByText('First steps (fictional)')
    await user.click(screen.getByText('bank-letters', { selector: '.mantine-NavLink-label' }))
    expect(vi.mocked(kh.files)).toHaveBeenLastCalledWith('case-1', { folder: 'bank-letters' })
  })

  it('shows no switch for withdrawn files: the team never sees them, and an overseer sees them in red with who withdrew them and why', async () => {
    const withdrawn = {
      kind: 'evidence', id: 'e2', display_id: 'EV-0002', title: 'Bank admin statement (fictional)', folder: 'bank-letters', status: 'withdrawn', sealed: false, type: 'bank_statement', created_by: ARUN,
      created_at: '2026-11-07T10:00:00Z', updated_at: '2026-11-07T10:00:00Z', version_number: null, withdrawn_reason: 'Uploaded to the wrong case (fictional)', withdrawn_at: '2026-11-08T09:00:00Z', withdrawn_by: ARUN,
      evidence: { mime_type: 'application/pdf', size_bytes: 1024 },
    }
    vi.mocked(kh.files).mockResolvedValue({ ...FILES, files: [...FILES.files, withdrawn] } as unknown as FilesView)
    page(<FilesTab />, detail({ add_files: true }))
    await screen.findByText('First steps (fictional)')
    expect(screen.queryByRole('switch', { name: /withdrawn/i })).toBeNull()
    expect(vi.mocked(kh.files)).toHaveBeenLastCalledWith('case-1', { folder: undefined })
    const row = screen.getByText('Bank admin statement (fictional)').closest('tr')!
    expect(row).toHaveAttribute('data-withdrawn', 'true')
    expect(within(row).getByText('withdrawn')).toBeInTheDocument()
    expect(within(row).getByText(/Withdrawn by .*Arun.*Uploaded to the wrong case \(fictional\)/)).toBeInTheDocument()
    expect(screen.getByText('Withdrawn by the team')).toBeInTheDocument()
    expect(screen.getByText('First steps (fictional)').closest('tr')).not.toHaveAttribute('data-withdrawn')
  })

  it('opens a note with its versions, and withdrawing needs a reason and is sent as a withdrawal, not a deletion', async () => {
    vi.mocked(kh.files).mockResolvedValue(FILES)
    vi.mocked(kh.artifactVersions).mockResolvedValue({
      id: 'n1', display_id: 'NOTE-0001', title: 'First steps (fictional)', artifact_type: 'note', folder: 'case-information', status: 'active', withdrawn_reason: null, case: {},
      sealed: false, sealed_reason: null, sealed_by: null, sealed_at: null,
      versions: [
        { id: 'v1', version_number: 1, content: { text: 'Complainant interviewed.' }, content_sha256: 'x', derived_from: [], author: ARUN, created_at: '2026-11-07T10:00:00Z', change_note: null },
        { id: 'v2', version_number: 2, content: { text: 'Complainant interviewed.\nBank written to.' }, content_sha256: 'y', derived_from: [], author: ARUN, created_at: '2026-11-07T11:00:00Z', change_note: 'Added the bank letter' },
      ],
      can: { revise: true, withdraw: true, seal: false },
    } as unknown as ArtifactHistory)
    vi.mocked(kh.withdrawNote).mockResolvedValue({} as never)
    const user = userEvent.setup()
    page(<FilesTab />, detail({ add_files: true, withdraw: true }), '/kh/case/case-1/files?open=n1')
    expect(await screen.findByText('version 2 of 2')).toBeInTheDocument()
    expect(screen.getByText('“Added the bank letter”')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'New version' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Seal' })).toBeNull() // only the supervisor or an administrator seals
    await user.click(screen.getByRole('button', { name: 'Withdraw' }))
    const dialog = await screen.findByRole('dialog', { name: /Withdraw First steps/ })
    const confirm = within(dialog).getByRole('button', { name: 'Withdraw' })
    expect(confirm).toBeDisabled()
    await user.type(within(dialog).getByRole('textbox'), 'Entered by mistake (fictional)')
    await user.click(confirm)
    expect(vi.mocked(kh.withdrawNote)).toHaveBeenCalledWith('n1', 'Entered by mistake (fictional)')
  })
})

describe('TeamTab', () => {
  const TEAM = {
    case: {},
    team: [
      { user: ARUN, role: 'lead', granted_by: null, granted_at: '2026-11-07T10:00:00Z', revoked_by: null, revoked_at: null },
      { user: MEERA, role: 'sub_investigator', granted_by: ARUN, granted_at: '2026-11-08T10:00:00Z', revoked_by: null, revoked_at: null },
      { user: { id: 'u-old', username: 'ana.old', display_name: 'Analyst Old (fictional)' }, role: 'analyst', granted_by: ARUN, granted_at: '2026-11-08T10:00:00Z', revoked_by: ARUN, revoked_at: '2026-11-09T10:00:00Z' },
    ],
  } as unknown as TeamView

  beforeEach(() => {
    vi.mocked(kh.team).mockResolvedValue(TEAM)
    vi.mocked(kh.accessHistory).mockResolvedValue([])
    vi.mocked(kh.removeMember).mockResolvedValue(TEAM)
  })

  it('lets the Investigator add people straight in and take a member off with a reason, but never the lead', async () => {
    const user = userEvent.setup()
    page(<TeamTab />, detail({ manage_team: true, add_files: true }))
    expect(await screen.findByText('ASI Meera (fictional)')).toBeInTheDocument()
    expect(screen.getByText('Sub Investigator')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Add team member' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Hand over the case' })).toBeNull() // that is for the Supervisor or an administrator
    // One "Take off" button: for Meera. The lead has none, and the person who already left has none.
    const buttons = screen.getAllByRole('button', { name: 'Take off the team' })
    expect(buttons).toHaveLength(1)
    await user.click(buttons[0])
    const dialog = await screen.findByRole('dialog')
    await user.type(within(dialog).getByRole('textbox'), 'Moved to another case (fictional)')
    await user.click(within(dialog).getByRole('button', { name: 'Take off the team' }))
    expect(vi.mocked(kh.removeMember)).toHaveBeenCalledWith('case-1', 'u-meera', 'Moved to another case (fictional)')
  })

  it('shows a Sub Investigator the team without any way to change it, and the Supervisor the hand-over', async () => {
    page(<TeamTab />, detail({}, { my_role: 'sub_investigator' }))
    expect(await screen.findByText('ASI Meera (fictional)')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Add team member' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Take off the team' })).toBeNull()
  })

  it('offers the hand-over to those who oversee the case', async () => {
    page(<TeamTab />, detail({ manage_team: true, hand_over: true }, { my_role: null }))
    expect(await screen.findByRole('button', { name: 'Hand over the case' })).toBeInTheDocument()
  })
})

describe('HistoryTab', () => {
  const ENTRIES = {
    case: {},
    entries: [
      { seq: 1, kind: 'case_registered', at: '2026-11-07T10:00:00Z', actor: ARUN, summary: 'Case KH-2026-0009 registered', subject_type: null, subject_id: null, details: {} },
      { seq: 2, kind: 'note_added', at: '2026-11-07T10:05:00Z', actor: ARUN, summary: 'Note NOTE-0001 added to case-information', subject_type: 'note', subject_id: 'n1', details: {} },
    ],
    next_after: null,
  } as unknown as HistoryView

  beforeEach(() => {
    vi.mocked(kh.history).mockResolvedValue(ENTRIES)
    vi.mocked(kh.historyCheck).mockReset()
  })

  it('lists the entries by number, with what happened and who did it', async () => {
    page(<HistoryTab />, detail({}))
    expect(await screen.findByText('Case KH-2026-0009 registered')).toBeInTheDocument()
    expect(screen.getByText('Note NOTE-0001 added to case-information')).toBeInTheDocument()
    expect(screen.getByText('Case registered')).toBeInTheDocument()
    expect(screen.getByText('Note added')).toBeInTheDocument()
    expect(vi.mocked(kh.history)).toHaveBeenCalledWith('case-1', { limit: 100, after: undefined })
  })

  it('says "History is intact" when the check passes', async () => {
    vi.mocked(kh.historyCheck).mockResolvedValue({ entries: 2, intact: true, first_problem: null, problem: null } as HistoryCheck)
    const user = userEvent.setup()
    page(<HistoryTab />, detail({}))
    await screen.findByText('Case KH-2026-0009 registered')
    await user.click(screen.getByRole('button', { name: 'Check the history' }))
    expect(await screen.findByText('History is intact')).toBeInTheDocument()
    expect(screen.getByText(/All 2 entries were checked/)).toBeInTheDocument()
  })

  it('names the first entry that does not check out, and what to do', async () => {
    vi.mocked(kh.historyCheck).mockResolvedValue({ entries: 2, intact: false, first_problem: 2, problem: 'entry 2 was changed after it was written' } as HistoryCheck)
    const user = userEvent.setup()
    page(<HistoryTab />, detail({}))
    await screen.findByText('Case KH-2026-0009 registered')
    await user.click(screen.getByRole('button', { name: 'Check the history' }))
    expect(await screen.findByText('The history does not check out')).toBeInTheDocument()
    expect(screen.getByText(/The first problem is at entry 2: entry 2 was changed after it was written/)).toBeInTheDocument()
  })
})

describe('OverviewTab', () => {
  beforeEach(() => {
    vi.mocked(kh.history).mockResolvedValue({
      case: {},
      entries: [{ seq: 7, kind: 'evidence_added', at: '2026-11-07T10:05:00Z', actor: ARUN, summary: 'Exhibit EV-0001 added to bank-letters', subject_type: null, subject_id: null, details: {} }],
      next_after: null,
    } as unknown as HistoryView)
    vi.mocked(kh.caseGovernance).mockResolvedValue({ holds: [], on_hold: false, decisions: [], policy: null, closed_at: null, review_due_on: null, review_due: false, can_decide: false, actions: [] } as never)
  })

  it('shows the folders made at registration, the recent entries and the team, with no repository, branch or commit anywhere', async () => {
    page(
      <OverviewTab />,
      detail({}, { team: [{ user: ARUN, role: 'lead', granted_by: null, granted_at: '2026-11-07T10:00:00Z', revoked_by: null, revoked_at: null }] }),
      '/kh/case/case-1',
    )
    expect(await screen.findByText('case-information')).toBeInTheDocument()
    expect(screen.getByText('bank-letters')).toBeInTheDocument()
    expect(await screen.findByText('Exhibit EV-0001 added to bank-letters')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Entry 7' })).toHaveAttribute('href', '/kh/case/case-1/history#entry-7')
    expect(screen.getByText('Investigator (case lead)')).toBeInTheDocument()
    expect(screen.queryByText(/repositor|branch|commit|clone|review request/i)).toBeNull()
  })

  it('offers the hand-over and the status change only to those who may', async () => {
    const view = page(<OverviewTab />, detail({}), '/kh/case/case-1')
    await screen.findByText('case-information')
    for (const name of ['Hand over the case', 'Change case status', 'Record official status']) expect(screen.queryByRole('button', { name })).toBeNull()
    view.unmount()
    page(<OverviewTab />, detail({ hand_over: true, change_workflow_status: true, change_official_status: true }, { my_role: null }), '/kh/case/case-1')
    for (const name of ['Hand over the case', 'Change case status', 'Record official status']) expect(await screen.findByRole('button', { name })).toBeInTheDocument()
  })

  it('says who reported the case: the person, "Unknown", or nothing recorded', async () => {
    const person = { unknown: false, name: 'Meera Nair (fictional)', phone: '+91 70000 00001', email: 'meera@example.invalid', address: '12 Example Road' }
    const first = page(<OverviewTab />, detail({}, { reported_by: person }), '/kh/case/case-1')
    expect(await screen.findByText('Meera Nair (fictional)')).toBeInTheDocument()
    expect(screen.getByText('+91 70000 00001 · meera@example.invalid')).toBeInTheDocument()
    expect(screen.getByText('12 Example Road')).toBeInTheDocument()
    first.unmount()
    const second = page(<OverviewTab />, detail({}, { reported_by: { unknown: true, name: null, phone: null, email: null, address: null } }), '/kh/case/case-1')
    await screen.findByText('case-information')
    expect(screen.getByText('Reported by').parentElement).toHaveTextContent('Unknown')
    second.unmount()
    page(<OverviewTab />, detail({}, { reported_by: null }), '/kh/case/case-1')
    await screen.findByText('case-information')
    expect(screen.getByText('Reported by').parentElement).toHaveTextContent('not recorded')
  })

  it('shows the description the way it was written, and the plain text when it has no formatting', async () => {
    const styled = page(<OverviewTab />, detail({}, { description_html: '<p><strong>Urgent</strong> complaint</p><script>steal()</script>' }), '/kh/case/case-1')
    expect((await screen.findByText('Urgent')).tagName).toBe('STRONG')
    expect(document.querySelector('script')).toBeNull()
    expect(screen.queryByText('Fictional: three transfers.')).toBeNull()
    styled.unmount()
    page(<OverviewTab />, detail({}), '/kh/case/case-1')
    expect(await screen.findByText('Fictional: three transfers.')).toBeInTheDocument()
  })
})

describe('CaseNumberDialog', () => {
  it('changes the number with a reason, refuses a malformed or unchanged number, and says the old number is kept', async () => {
    vi.mocked(kh.changeCaseNumber).mockResolvedValue({ display_id: 'PS-CYB-2026/14' } as unknown as CaseDetail)
    const onClose = vi.fn()
    const user = userEvent.setup()
    renderWithProviders(<CaseNumberDialog opened onClose={onClose} detail={detail({ rename_case: true })} />, '/kh/case/case-1')
    const change = await screen.findByRole('button', { name: 'Change number' })
    expect(screen.getByLabelText('Current number')).toHaveValue('KH-2026-0009')
    expect(screen.getByText(/The old number is kept: it still finds the case/)).toBeInTheDocument()
    expect(change).toBeDisabled()
    await user.type(screen.getByLabelText('New case number'), 'kh-2026-0009')
    expect(await screen.findByText('This is already the number of the case')).toBeInTheDocument()
    await user.clear(screen.getByLabelText('New case number'))
    await user.type(screen.getByLabelText('New case number'), 'a;b')
    expect(await screen.findByText(/3 to 32 letters, digits/)).toBeInTheDocument()
    await user.clear(screen.getByLabelText('New case number'))
    await user.type(screen.getByLabelText('New case number'), '  PS-CYB-2026/14 ')
    expect(change).toBeDisabled() // a reason is needed
    await user.type(screen.getByLabelText(/Reason/), 'The station file number (fictional)')
    await user.click(change)
    expect(kh.changeCaseNumber).toHaveBeenCalledWith('case-1', { number: 'PS-CYB-2026/14', reason: 'The station file number (fictional)' })
    await vi.waitFor(() => expect(onClose).toHaveBeenCalled())
  })
})
