// Officers create their own login, the sign-in page offers it, and the people above can raise the new login's clearance. All names are fictional.

import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as endpoints from '../api/endpoints'
import { AuthContext, type AuthValue } from '../auth/context'
import { kh } from '../kh/api'
import { PeoplePage } from '../kh/pages/PeoplePage'
import type { AccountRow, PeopleCapabilities } from '../kh/types'
import { renderWithProviders } from '../test/render'
import { CreateAccountPage } from './CreateAccountPage'
import { LoginPage } from './LoginPage'

vi.mock('../api/endpoints', async (original) => ({
  ...(await original<typeof import('../api/endpoints')>()),
  registrationStatus: vi.fn(),
  registerYourself: vi.fn(),
}))
vi.mock('../kh/api', () => ({
  kh: { peopleCapabilities: vi.fn(), accounts: vi.fn(), officers: vi.fn(), peopleStations: vi.fn(), changeClearance: vi.fn() },
  newKey: () => 'key',
}))

const signedOut: AuthValue = { user: null, loading: false, login: vi.fn(), loginSecondStep: vi.fn(), logout: vi.fn(), refresh: vi.fn() } as unknown as AuthValue
const withAuth = (ui: ReactNode, value: AuthValue = signedOut) => <AuthContext.Provider value={value}>{ui}</AuthContext.Provider>

describe('CreateAccountPage', () => {
  beforeEach(() => {
    vi.mocked(endpoints.registrationStatus).mockResolvedValue({ enabled: true })
  })

  async function fill(user: ReturnType<typeof userEvent.setup>, over: { again?: string } = {}) {
    await user.type(screen.getByLabelText(/^Officer ID/), 'INV-9')
    await user.type(screen.getByLabelText(/^Full name/), 'Ravi Kumar (fictional)')
    await user.type(screen.getByLabelText(/^Username/), 'ravi.kumar')
    await user.type(screen.getByLabelText(/^Password/), 'My-own-fictional-pass-1')
    await user.type(screen.getByLabelText(/^Repeat the password/), over.again ?? 'My-own-fictional-pass-1')
  }

  it('sends only the four things, and tells the officer their login starts with view-only access', async () => {
    const user = userEvent.setup()
    vi.mocked(endpoints.registerYourself).mockResolvedValue({
      username: 'ravi.kumar', display_name: 'Ravi Kumar (fictional)', org_role: 'viewer', station: 'PS-A',
      message: 'Your login is ready. It starts with view-only access: your Supervisor or Administrator can give you more.',
    })
    renderWithProviders(withAuth(<CreateAccountPage />), '/create-account')
    const submit = await screen.findByRole('button', { name: 'Create my login' })
    expect(submit).toBeDisabled()
    await fill(user)
    expect(submit).toBeEnabled()
    await user.click(submit)
    expect(await screen.findByText('Your login is ready')).toBeInTheDocument()
    expect(endpoints.registerYourself).toHaveBeenCalledWith({ officer_number: 'INV-9', full_name: 'Ravi Kumar (fictional)', username: 'ravi.kumar', password: 'My-own-fictional-pass-1', email: null, phone: null })
    expect(screen.getByText(/view-only access/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Log in as ravi.kumar' })).toHaveAttribute('href', '/login')
  })

  it('can fill in the profile right away (email and phone are optional) and refuses ones that look wrong', async () => {
    const user = userEvent.setup()
    vi.mocked(endpoints.registerYourself).mockResolvedValue({ username: 'ravi.kumar', display_name: 'Ravi Kumar (fictional)', org_role: 'viewer', station: 'PS-A', message: 'Your login is ready.' })
    renderWithProviders(withAuth(<CreateAccountPage />), '/create-account')
    await screen.findByRole('button', { name: 'Create my login' })
    await fill(user)
    await user.type(screen.getByLabelText(/^Email/), 'not an email')
    expect(screen.getByText('Not a valid email address')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Create my login' })).toBeDisabled()
    await user.clear(screen.getByLabelText(/^Email/))
    await user.type(screen.getByLabelText(/^Email/), 'ravi@example.invalid')
    await user.type(screen.getByLabelText(/^Phone/), '+91 70000 00001')
    await user.click(screen.getByRole('button', { name: 'Create my login' }))
    await screen.findByRole('heading', { name: 'Your login is ready' })
    expect(endpoints.registerYourself).toHaveBeenCalledWith(expect.objectContaining({ email: 'ravi@example.invalid', phone: '+91 70000 00001' }))
  })

  it('does not let the two passwords differ or a short one through', async () => {
    const user = userEvent.setup()
    renderWithProviders(withAuth(<CreateAccountPage />), '/create-account')
    await screen.findByRole('button', { name: 'Create my login' })
    await fill(user, { again: 'Something-else-entirely-9' })
    expect(screen.getByText('The two passwords are not the same')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Create my login' })).toBeDisabled()
  })

  it("shows the server's refusal as it is", async () => {
    const user = userEvent.setup()
    vi.mocked(endpoints.registerYourself).mockRejectedValue(new Error("These details don't match the officer register, or this officer already has an account."))
    renderWithProviders(withAuth(<CreateAccountPage />), '/create-account')
    await screen.findByRole('button', { name: 'Create my login' })
    await fill(user)
    await user.click(screen.getByRole('button', { name: 'Create my login' }))
    expect(await screen.findByText(/don't match the officer register/)).toBeInTheDocument()
    expect(screen.queryByText('Your login is ready')).toBeNull()
  })

  it('says so when creating your own login is switched off', async () => {
    vi.mocked(endpoints.registrationStatus).mockResolvedValue({ enabled: false })
    renderWithProviders(withAuth(<CreateAccountPage />), '/create-account')
    expect(await screen.findByText('Creating your own login is switched off')).toBeInTheDocument()
    expect(screen.queryByLabelText(/^Officer ID/)).toBeNull()
  })
})

describe('LoginPage', () => {
  it('offers to create your own login when that is switched on, and never when it is off', async () => {
    vi.mocked(endpoints.registrationStatus).mockResolvedValue({ enabled: true })
    const first = renderWithProviders(withAuth(<LoginPage />), '/login')
    expect(await screen.findByRole('link', { name: 'Create your own login' })).toHaveAttribute('href', '/create-account')
    first.unmount()
    vi.mocked(endpoints.registrationStatus).mockResolvedValue({ enabled: false })
    renderWithProviders(withAuth(<LoginPage />), '/login')
    await screen.findByText('Log in', { selector: 'h1' })
    await waitFor(() => expect(endpoints.registrationStatus).toHaveBeenCalledTimes(2))
    expect(screen.queryByRole('link', { name: 'Create your own login' })).toBeNull()
  })

  it('no longer talks about repositories, clones, branches or merges', async () => {
    vi.mocked(endpoints.registrationStatus).mockResolvedValue({ enabled: true })
    renderWithProviders(withAuth(<LoginPage />), '/login')
    await screen.findByText('Log in', { selector: 'h1' })
    expect(document.body.textContent).not.toMatch(/repositor|clone|branch|merge|commit/i)
    expect(screen.getByText('History is never rewritten')).toBeInTheDocument()
  })
})

describe('People: change clearance', () => {
  const row = (over: Partial<AccountRow['can']> = {}): AccountRow =>
    ({
      id: 'u-ravi', username: 'ravi.kumar', display_name: 'Ravi Kumar (fictional)', org_role: 'viewer', clearance: 'public', is_active: true,
      must_change_password: false, org_role_since: null, last_login_at: null, officer: null, stations: [],
      can: { change_role: true, allowed_roles: ['analyst'], change_clearance: true, allowed_clearances: ['internal', 'restricted'], set_stations: false,
             reset_password: true, deactivate: true, reactivate: false, ...over },
    }) as unknown as AccountRow
  const supervisor: AuthValue = { ...signedOut, user: { id: 's1', username: 'sup', display_name: 'Sup', role: 'analyst', clearance: 'restricted', org_role: 'supervisor', organization_id: 'o1' } } as unknown as AuthValue

  beforeEach(() => {
    vi.mocked(kh.peopleCapabilities).mockResolvedValue({ role: 'supervisor', create_roles: [], can_create_accounts: false, can_manage_people: true, can_enter_officers: false, can_manage_stations: false, sees_people: true } as PeopleCapabilities)
    vi.mocked(kh.officers).mockResolvedValue([])
    vi.mocked(kh.peopleStations).mockResolvedValue([])
  })

  it('offers it only to those who may, with only the levels they may give, and asks for a reason', async () => {
    const user = userEvent.setup()
    vi.mocked(kh.accounts).mockResolvedValue([row()])
    vi.mocked(kh.changeClearance).mockResolvedValue({ ...row(), clearance: 'restricted' })
    renderWithProviders(withAuth(<PeoplePage />, supervisor), '/kh/people')
    await user.click(await screen.findByRole('button', { name: 'Actions for Ravi Kumar (fictional)' }))
    await user.click(await screen.findByRole('menuitem', { name: 'Change clearance…' }))
    expect(screen.getByText('Now:', { exact: false }).textContent).toContain('Public')
    const change = screen.getByRole('button', { name: 'Change clearance' })
    expect(change).toBeDisabled()
    await user.click(screen.getByRole('combobox', { name: /New clearance/ }))
    expect(await screen.findByRole('option', { name: 'Internal', hidden: true })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'Confidential', hidden: true })).toBeNull() // above the Supervisor's own
    expect(screen.queryByRole('option', { name: 'Public', hidden: true })).toBeNull() // the level they already have
    await user.click(screen.getByRole('option', { name: 'Restricted', hidden: true }))
    await user.type(screen.getByLabelText(/^Reason/), 'Works on restricted cases (fictional)')
    await user.click(change)
    await waitFor(() => expect(kh.changeClearance).toHaveBeenCalledWith('u-ravi', 'restricted', 'Works on restricted cases (fictional)'))
  })

  it('is not offered for someone the viewer does not look after', async () => {
    const user = userEvent.setup()
    vi.mocked(kh.accounts).mockResolvedValue([row({ change_clearance: false, allowed_clearances: [] })])
    renderWithProviders(withAuth(<PeoplePage />, supervisor), '/kh/people')
    await user.click(await screen.findByRole('button', { name: 'Actions for Ravi Kumar (fictional)' }))
    await screen.findByRole('menuitem', { name: 'Change role…' })
    expect(screen.queryByRole('menuitem', { name: 'Change clearance…' })).toBeNull()
  })
})
