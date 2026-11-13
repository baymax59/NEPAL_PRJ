// Station and officer dashboards (phase R-5). Fictional data. The figures come from the server; these tests check that the screens
// show them in plain words, say "—" where there is nothing to average, and flag ended accounts.

import { screen, within } from '@testing-library/react'
import type { ReactNode } from 'react'
import { Route, Routes } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import { AuthContext, type AuthValue } from '../../auth/context'
import type { UserOut } from '../../api/types'
import { renderWithProviders } from '../../test/render'
import { kh } from '../api'
import type { OfficerDashboard, StationDashboard, StationsOverview } from '../types'
import { OfficerPerformancePage, PerformancePage, StationPerformancePage } from './PerformancePage'

vi.mock('../api', () => ({ kh: { dashboardStations: vi.fn(), dashboardStation: vi.fn(), dashboardOfficer: vi.fn() } }))

const as = (org_role: string): AuthValue => ({
  user: { id: 'me', username: 'someone', display_name: 'Someone (fictional)', org_role } as unknown as UserOut,
  loading: false,
  login: vi.fn(),
  loginSecondStep: vi.fn(),
  logout: vi.fn(),
  reload: vi.fn(),
  hasRole: () => true,
})

const FIGURES = (over: Record<string, unknown> = {}) => ({
  total: 6, open: 4, closed: 2, pending_evidence: 1, pending_review: 1, by_status: { open: 2, closed: 2, pending_evidence: 1, pending_review: 1 },
  new_this_month: 3, average_days_to_close: 2.5,
  oldest_open: [{ case: { id: 'c1', display_id: 'KH-2026-0001', title: 'Online fraud (fictional)', workflow_status: 'pending_evidence', priority: 'high' }, opened_at: '2026-10-01T00:00:00Z', days_open: 40 }],
  ...over,
})
const STATION = (code: string, over: Record<string, unknown> = {}) => ({
  station: { id: `id-${code}`, code, name: `${code} police station (fictional)`, district: 'Example district', status: 'active' },
  figures: FIGURES(over),
  officers: 3,
})

function page(ui: ReactNode, auth: AuthValue, path: string) {
  return renderWithProviders(
    <AuthContext.Provider value={auth}>
      <Routes>
        <Route path="/kh/performance" element={ui} />
        <Route path="/kh/performance/stations/:stationId" element={ui} />
        <Route path="/kh/performance/officers/:userId" element={ui} />
      </Routes>
    </AuthContext.Provider>,
    path,
  )
}

describe('PerformancePage', () => {
  it('lists each station with its open, closed and pending cases, and says "—" when nothing has been closed', async () => {
    vi.mocked(kh.dashboardStations).mockResolvedValue({
      stations: [STATION('PS-A'), STATION('PS-B', { total: 1, open: 1, closed: 0, pending_evidence: 0, pending_review: 0, average_days_to_close: null, oldest_open: [] })],
      generated_at: '2026-11-10T10:00:00Z',
    } as unknown as StationsOverview)
    page(<PerformancePage />, as('super_admin'), '/kh/performance')
    const a = (await screen.findByRole('link', { name: 'PS-A' })).closest('tr') as HTMLElement
    expect(within(a).getByText('2.5 days')).toBeInTheDocument()
    expect(within(a).getByRole('link', { name: 'KH-2026-0001' })).toBeInTheDocument()
    expect(within(a).getByText('40 days')).toBeInTheDocument()
    const b = screen.getByRole('link', { name: 'PS-B' }).closest('tr') as HTMLElement
    expect(within(b).queryByText(/days/)).not.toBeInTheDocument() // no average, no oldest case: dashes only
    expect(screen.getByText('Pending case')).toBeInTheDocument()
    expect(screen.getByText(/means not closed or archived/)).toBeInTheDocument() // the words used are explained
  })

  it('shows an Administrator with no station what to do', async () => {
    vi.mocked(kh.dashboardStations).mockResolvedValue({ stations: [], generated_at: '2026-11-10T10:00:00Z' } as unknown as StationsOverview)
    page(<PerformancePage />, as('administrator'), '/kh/performance')
    expect(await screen.findByText('No police station')).toBeInTheDocument()
  })
})

describe('StationPerformancePage', () => {
  it('shows the figures, the cases open the longest, and each officer', async () => {
    const officer = (name: string, late: number) => ({
      person: { id: name, username: name, display_name: `${name} (fictional)`, org_role: 'investigator', is_active: true, officer: { officer_number: 'X1', full_name: name, rank: 'Inspector' }, stations: [] },
      cases: { total: 2, open: 2, closed: 0, pending_evidence: 1, pending_review: 0 },
      tasks: { done: 4, open: 1, late },
      work: { entries: 9, entries_last_30_days: 5, notes: 3, evidence: 2 },
      last_activity: '2026-11-09T10:00:00Z',
    })
    vi.mocked(kh.dashboardStation).mockResolvedValue({
      ...STATION('PS-A'),
      monthly: [{ month: '2026-10', opened: 2, closed: 1 }, { month: '2026-11', opened: 3, closed: 0 }],
      officers: [officer('arun', 2), officer('meena', 0)],
      generated_at: '2026-11-10T10:00:00Z',
    } as unknown as StationDashboard)
    page(<StationPerformancePage />, as('supervisor'), '/kh/performance/stations/id-PS-A')
    expect(await screen.findByRole('heading', { name: /PS-A · PS-A police station/ })).toBeInTheDocument()
    expect(screen.getByText('Open cases')).toBeInTheDocument()
    expect(screen.getByText('2.5 days')).toBeInTheDocument()
    const arun = screen.getByRole('link', { name: 'arun (fictional)' }).closest('tr') as HTMLElement
    expect(within(arun).getByText('Investigator · Inspector')).toBeInTheDocument()
    // Officer, Cases, Open, Pending, Closed, Notes written, Exhibits added, Last activity (no task columns)
    expect(within(arun).getAllByRole('cell').map((c) => c.textContent).slice(1, 7)).toEqual(['2', '2', '1', '0', '3', '2'])
    expect(screen.queryByText(/tasks/i)).toBeNull()
    const meena = screen.getByRole('link', { name: 'meena (fictional)' }).closest('tr') as HTMLElement
    expect(within(meena).getAllByRole('cell')[5]).toHaveTextContent('3')
  })
})

describe('OfficerPerformancePage', () => {
  const OFFICER = (over: Record<string, unknown> = {}) =>
    ({
      person: { id: 'u1', username: 'inv.arun', display_name: 'SI Arun (fictional)', org_role: 'investigator', is_active: true, officer: { officer_number: 'KH-1001', full_name: 'Arun', rank: 'Sub-Inspector' }, stations: [{ id: 's', code: 'PS-A', name: 'x' }] },
      cases: { total: 2, open: 1, closed: 1, pending_evidence: 1, pending_review: 0 },
      tasks: { done: 3, open: 1, late: 2 },
      work: { entries: 9, entries_last_30_days: 5, notes: 3, evidence: 2 },
      last_activity: '2026-11-09T10:00:00Z',
      case_list: [
        { case: { id: 'c1', display_id: 'KH-2026-0001', title: 'Online fraud (fictional)', workflow_status: 'pending_evidence', priority: 'high' }, station_code: 'PS-A', roles: ['lead'], active: true, opened_at: '2026-10-01T00:00:00Z', days_open: 40 },
        { case: { id: 'c2', display_id: 'KH-2026-0002', title: 'Old matter (fictional)', workflow_status: 'closed', priority: 'low' }, station_code: 'PS-A', roles: ['contributor'], active: false, opened_at: '2026-09-01T00:00:00Z', days_open: null },
      ],
      generated_at: '2026-11-10T10:00:00Z',
      ...over,
    }) as unknown as OfficerDashboard

  it("shows an officer's progress, their cases, and where they are no longer on a case", async () => {
    vi.mocked(kh.dashboardOfficer).mockResolvedValue(OFFICER())
    page(<OfficerPerformancePage />, as('supervisor'), '/kh/performance/officers/u1')
    expect(await screen.findByRole('heading', { name: 'SI Arun (fictional)' })).toBeInTheDocument()
    expect(screen.getByText(/Investigator · Sub-Inspector · ID KH-1001 · PS-A/)).toBeInTheDocument()
    expect(screen.queryByText(/tasks/i)).toBeNull()
    expect(screen.getByText('Notes written').nextElementSibling).toHaveTextContent('3')
    expect(screen.getByText('History entries, last 30 days').nextElementSibling).toHaveTextContent('5')
    const rows = screen.getAllByRole('row')
    const old = rows.find((r) => r.textContent?.includes('KH-2026-0002')) as HTMLElement
    expect(within(old).getByText('no longer on it')).toBeInTheDocument()
    expect(within(old).getByText('closed', { selector: 'td' })).toBeInTheDocument() // no "open for" once closed
    expect(within(old).getByText('Sub Investigator')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Station dashboards' })).toBeInTheDocument() // a way back for someone looking at another officer
  })

  it('says so when the account has ended, and offers no way back on your own page', async () => {
    vi.mocked(kh.dashboardOfficer).mockResolvedValue(OFFICER({ person: { ...OFFICER().person, id: 'me', is_active: false } }))
    page(<OfficerPerformancePage />, as('investigator'), '/kh/performance/officers/me')
    expect(await screen.findByText(/This account has ended/)).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Station dashboards' })).not.toBeInTheDocument()
    expect(screen.getByText('My performance')).toBeInTheDocument()
  })
})
