// My profile: the official details are only shown; email, phone and job title are filled in and updated by the person. All names are fictional.

import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as endpoints from '../../api/endpoints'
import type { Profile } from '../../api/types'
import { AuthContext, type AuthValue } from '../../auth/context'
import { renderWithProviders } from '../../test/render'
import { kh } from '../api'
import type { MyCase } from '../types'
import { MyProfilePage } from './MyProfilePage'

vi.mock('../../api/endpoints', async (original) => ({
  ...(await original<typeof import('../../api/endpoints')>()),
  getProfile: vi.fn(),
  saveProfile: vi.fn(),
  uploadPhoto: vi.fn(),
  removePhoto: vi.fn(),
  fetchPhoto: vi.fn(),
}))

vi.mock('../api', () => ({ kh: { myCases: vi.fn() }, newKey: () => 'key' }))

const team = (id: string, number: string, title: string, role: string): MyCase =>
  ({ case: { id, display_id: number, title, workflow_status: 'under_investigation', priority: 'high', classification: 'restricted' }, role, active_from: '2026-11-07T10:00:00Z', last_activity: '2026-11-09T10:00:00Z' }) as unknown as MyCase

const reload = vi.fn().mockResolvedValue(undefined)
const auth = { user: null, loading: false, login: vi.fn(), loginSecondStep: vi.fn(), logout: vi.fn(), reload, hasRole: vi.fn() } as unknown as AuthValue
const page = () => renderWithProviders(<AuthContext.Provider value={auth}><MyProfilePage /></AuthContext.Provider>, '/kh/profile')

const profile = (over: Partial<Profile> = {}): Profile => ({
  username: 'ravi.kumar', display_name: 'Ravi Kumar (fictional)', org_role: 'viewer', clearance: 'public', officer_number: 'INV-9', rank: 'Inspector',
  stations: ['PS-A'], email: null, phone: null, job_title: null, profile_updated_at: null, ...over,
})

describe('MyProfilePage', () => {
  beforeEach(() => {
    reload.mockClear()
    URL.createObjectURL = vi.fn(() => 'blob:photo')
    vi.mocked(endpoints.fetchPhoto).mockResolvedValue(new Blob(['x'], { type: 'image/jpeg' }))
    vi.mocked(kh.myCases).mockResolvedValue([])
  })

  it('shows the teams the person is on, with their part in each, and says so when there are none', async () => {
    vi.mocked(endpoints.getProfile).mockResolvedValue(profile({ profile_updated_at: '2026-11-11T10:00:00Z' }))
    vi.mocked(kh.myCases).mockResolvedValue([
      team('c1', 'KH-2026-0001', 'Online banking fraud (fictional)', 'lead'),
      team('c2', 'KH-2026-0002', 'Missing person (fictional)', 'sub_investigator'),
    ])
    const first = page()
    expect(await screen.findByText('Teams I am on (2)')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Online banking fraud (fictional)' })).toHaveAttribute('href', '/kh/case/c1')
    expect(screen.getByText('Investigator (case lead)')).toBeInTheDocument()
    expect(screen.getByText('Sub Investigator')).toBeInTheDocument()
    first.unmount()
    vi.mocked(kh.myCases).mockResolvedValue([])
    page()
    expect(await screen.findByText('Not on any team yet')).toBeInTheDocument()
  })

  describe('the photo', () => {
    const input = () => document.querySelector('input[type="file"]') as HTMLInputElement
    const picture = (name = 'me.png', type = 'image/png', size = 1000) => new File([new Uint8Array(size)], name, { type })

    it('can be uploaded, shows what it accepts, and offers no removal while there is none', async () => {
      const user = userEvent.setup()
      vi.mocked(endpoints.getProfile).mockResolvedValue(profile({ id: 'u-ravi' }))
      vi.mocked(endpoints.uploadPhoto).mockResolvedValue(profile({ id: 'u-ravi', photo_updated_at: '2026-11-11T10:00:00Z' }))
      page()
      expect(await screen.findByRole('button', { name: 'Upload a photo' })).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Remove photo' })).toBeNull()
      expect(screen.getByText(/JPEG, PNG or WebP, up to 2 MB/)).toBeInTheDocument()
      const file = picture()
      await user.upload(input(), file)
      await waitFor(() => expect(endpoints.uploadPhoto).toHaveBeenCalledWith(file))
      await waitFor(() => expect(reload).toHaveBeenCalled()) // the top bar shows the new picture
    })

    it('refuses a file of the wrong kind or one that is too big, without asking the server', async () => {
      const user = userEvent.setup({ applyAccept: false })
      vi.mocked(endpoints.getProfile).mockResolvedValue(profile({ id: 'u-ravi' }))
      page()
      await screen.findByRole('button', { name: 'Upload a photo' })
      await user.upload(input(), picture('me.gif', 'image/gif'))
      expect(await screen.findByText('Use a JPEG, PNG or WebP picture')).toBeInTheDocument()
      await user.upload(input(), picture('big.png', 'image/png', 2 * 1024 * 1024 + 1))
      expect(await screen.findByText('The picture is larger than 2 MB: choose a smaller one')).toBeInTheDocument()
      expect(endpoints.uploadPhoto).not.toHaveBeenCalled()
    })

    it('can be changed and taken off once there is one', async () => {
      const user = userEvent.setup()
      vi.mocked(endpoints.getProfile).mockResolvedValue(profile({ id: 'u-ravi', photo_updated_at: '2026-11-11T10:00:00Z' }))
      vi.mocked(endpoints.removePhoto).mockResolvedValue(profile({ id: 'u-ravi', photo_updated_at: null }))
      page()
      expect(await screen.findByRole('button', { name: 'Change photo' })).toBeInTheDocument()
      await waitFor(() => expect(endpoints.fetchPhoto).toHaveBeenCalledWith('u-ravi'))  // the picture itself is fetched with the login
      await user.click(screen.getByRole('button', { name: 'Remove photo' }))
      await waitFor(() => expect(endpoints.removePhoto).toHaveBeenCalled())
    })
  })

  it('shows the official details as they are, asks for the profile when it is empty, and saves what the person fills in', async () => {
    const user = userEvent.setup()
    vi.mocked(endpoints.getProfile).mockResolvedValue(profile())
    vi.mocked(endpoints.saveProfile).mockResolvedValue(profile({ email: 'ravi@example.invalid', phone: '+91 70000 00001', job_title: 'Inspector, cyber cell', profile_updated_at: '2026-11-11T10:00:00Z' }))
    page()
    expect(await screen.findByText('Fill in your email and phone, so your Supervisor can reach you.')).toBeInTheDocument()
    for (const shown of ['Ravi Kumar (fictional)', '@ravi.kumar', 'INV-9', 'Inspector', 'PS-A']) expect(screen.getByText(shown)).toBeInTheDocument()
    expect(screen.getByText('Not filled in yet')).toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: /^Name/ })).toBeNull() // the official details cannot be edited here

    await user.type(screen.getByLabelText(/^Email/), '  ravi@example.invalid ')
    await user.type(screen.getByLabelText(/^Phone/), '+91 70000 00001')
    await user.type(screen.getByLabelText(/^Job title/), 'Inspector, cyber cell')
    await user.click(screen.getByRole('button', { name: 'Save my profile' }))
    await waitFor(() => expect(endpoints.saveProfile).toHaveBeenCalledWith({ email: 'ravi@example.invalid', phone: '+91 70000 00001', job_title: 'Inspector, cyber cell' }))
    await waitFor(() => expect(reload).toHaveBeenCalled()) // so the prompt on the dashboard goes away
  })

  it('does not save an email or phone that looks wrong', async () => {
    const user = userEvent.setup()
    vi.mocked(endpoints.getProfile).mockResolvedValue(profile())
    page()
    const save = await screen.findByRole('button', { name: 'Save my profile' })
    await user.type(screen.getByLabelText(/^Email/), 'not an email')
    expect(screen.getByText('Not a valid email address')).toBeInTheDocument()
    expect(save).toBeDisabled()
    await user.clear(screen.getByLabelText(/^Email/))
    await user.type(screen.getByLabelText(/^Phone/), 'call me')
    expect(screen.getByText(/Use digits, spaces/)).toBeInTheDocument()
    expect(save).toBeDisabled()
  })

  it('can clear a field, and offers nothing to save when nothing changed', async () => {
    const user = userEvent.setup()
    const saved = profile({ email: 'ravi@example.invalid', phone: '+91 70000 00001', job_title: 'Inspector', profile_updated_at: '2026-11-11T10:00:00Z' })
    vi.mocked(endpoints.getProfile).mockResolvedValue(saved)
    vi.mocked(endpoints.saveProfile).mockResolvedValue({ ...saved, job_title: null })
    page()
    const save = await screen.findByRole('button', { name: 'Save my profile' })
    expect(screen.queryByText('Fill in your email and phone, so your Supervisor can reach you.')).toBeNull() // it has been filled in
    expect(save).toBeDisabled()
    await user.clear(screen.getByLabelText(/^Job title/))
    expect(save).toBeEnabled()
    await user.click(save)
    await waitFor(() => expect(endpoints.saveProfile).toHaveBeenCalledWith({ email: 'ravi@example.invalid', phone: '+91 70000 00001', job_title: null }))
  })
})
