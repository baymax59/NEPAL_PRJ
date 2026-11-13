// Chat inside the case: the team group and private conversations; only the team; read-only once archived. All names are fictional.

import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthContext, type AuthValue } from '../../auth/context'
import { renderWithProviders } from '../../test/render'
import { kh } from '../api'
import { describeNotice } from '../labels'
import type { CaseDetail, ChatMessage, ChatThread } from '../types'
import { ChatTab } from './ChatTab'
import { CaseContext } from './context'

vi.mock('../api', () => ({
  kh: { chatThreads: vi.fn(), chatMessages: vi.fn(), chatSend: vi.fn(), chatRead: vi.fn() },
  newKey: () => 'key',
}))
vi.mock('../../components/UserAvatar', () => ({ UserAvatar: ({ name }: { name: string }) => <span data-testid="avatar">{name}</span> }))

const ARUN = { id: 'u-arun', username: 'inv.arun', display_name: 'SI Arun (fictional)' }
const MEERA = { id: 'u-meera', username: 'sub.meera', display_name: 'ASI Meera (fictional)' }
const DEV = { id: 'u-dev', username: 'dev.analyst', display_name: 'Dev Patel (fictional)' }

const detail = (can: Record<string, boolean> = { chat: true, write_chat: true }) => ({ id: 'case-1', display_id: 'KH-2026-0009', can }) as unknown as CaseDetail
const thread = (over: Partial<ChatThread> & Pick<ChatThread, 'key' | 'title'>): ChatThread =>
  ({ kind: over.key === 'group' ? 'group' : 'direct', peer: null, last: null, unread: 0, ...over }) as ChatThread
const message = (id: number, sender: typeof ARUN, body: string, mine = false, to: typeof ARUN | null = null): ChatMessage =>
  ({ id, sender, to, body, at: '2026-11-11T10:00:00Z', mine }) as unknown as ChatMessage

const THREADS = [
  thread({ key: 'group', title: 'The team', unread: 2, last: { id: 3, sender: MEERA, preview: 'Bring the call chart', at: '2026-11-11T10:05:00Z' } as ChatThread['last'] }),
  thread({ key: MEERA.id, title: MEERA.display_name, peer: MEERA }),
  thread({ key: DEV.id, title: DEV.display_name, peer: DEV, unread: 1 }),
]

const auth = { user: { id: ARUN.id, username: ARUN.username, display_name: ARUN.display_name, role: 'analyst', clearance: 'restricted', org_role: 'investigator', organization_id: 'o1' }, loading: false } as unknown as AuthValue

function page(can?: Record<string, boolean>, route = '/kh/case/case-1/chat') {
  return renderWithProviders(
    <AuthContext.Provider value={auth}>
      <CaseContext.Provider value={detail(can)}>
        <ChatTab />
      </CaseContext.Provider>
    </AuthContext.Provider>,
    route,
  )
}

describe('ChatTab', () => {
  beforeEach(() => {
    vi.mocked(kh.chatThreads).mockResolvedValue(THREADS)
    vi.mocked(kh.chatMessages).mockResolvedValue({ thread: 'group', messages: [message(1, ARUN, 'Meet at nine (fictional)', true), message(3, MEERA, 'Bring the call chart (fictional)')] })
    vi.mocked(kh.chatRead).mockResolvedValue(undefined as never)
    vi.mocked(kh.chatSend).mockResolvedValue(message(4, ARUN, 'ok', true))
  })

  it('lists the team and each other member with the unread counts, and shows the team conversation first', async () => {
    page()
    expect((await screen.findAllByText('The team', { selector: 'p' })).length).toBeGreaterThan(0)
    expect(screen.getByText(MEERA.display_name, { selector: 'p' })).toBeInTheDocument()
    expect(screen.getByLabelText('2 unread')).toBeInTheDocument()
    expect(screen.getByLabelText('1 unread')).toBeInTheDocument()
    expect(screen.getByText('ASI Meera (fictional): Bring the call chart')).toBeInTheDocument() // who wrote the latest message of the team conversation
    expect(await screen.findByText('Bring the call chart (fictional)')).toBeInTheDocument()
    expect(screen.getByText('Meet at nine (fictional)')).toBeInTheDocument()
    expect(kh.chatMessages).toHaveBeenCalledWith('case-1', 'group')
    // the team conversation names the writers of other people's messages
    expect(screen.getAllByText(MEERA.display_name, { selector: 'p' }).length).toBeGreaterThan(1)
    await waitFor(() => expect(kh.chatRead).toHaveBeenCalledWith('case-1', 'group', 3)) // reading it clears the unread count
  })

  it('opens a private conversation with one member, and what is written there goes to that person only', async () => {
    const user = userEvent.setup()
    vi.mocked(kh.chatMessages).mockImplementation(async (_case, key) =>
      key === DEV.id ? { thread: key, messages: [message(7, DEV, 'Only for you (fictional)', false, ARUN)] } : { thread: key, messages: [] })
    page()
    await user.click(await screen.findByRole('button', { name: /Dev Patel \(fictional\)/ }))
    expect(await screen.findByText('Only for you (fictional)')).toBeInTheDocument()
    expect(kh.chatMessages).toHaveBeenCalledWith('case-1', DEV.id)
    expect(screen.getByText(/Only you and Dev Patel \(fictional\) see this conversation/)).toBeInTheDocument()
    await user.type(screen.getByLabelText('Message'), 'On my way{Enter}')
    await waitFor(() => expect(kh.chatSend).toHaveBeenCalledWith('case-1', DEV.id, 'On my way'))
  })

  it('sends to the team with Enter, keeps a new line for Shift+Enter, and refuses a blank or an over-long message', async () => {
    const user = userEvent.setup()
    page()
    const box = await screen.findByLabelText('Message')
    const send = screen.getByRole('button', { name: 'Send' })
    expect(send).toBeDisabled()
    await user.type(box, '   ')
    expect(send).toBeDisabled()
    await user.clear(box)
    await user.type(box, 'Line one{Shift>}{Enter}{/Shift}Line two')
    expect(kh.chatSend).not.toHaveBeenCalled()
    await user.keyboard('{Enter}')
    await waitFor(() => expect(kh.chatSend).toHaveBeenCalledWith('case-1', null, 'Line one\nLine two'))
    await waitFor(() => expect(box).toHaveValue(''))
    await user.click(box)
    await user.paste('x'.repeat(4001))
    expect(await screen.findByText('At most 4000 characters')).toBeInTheDocument()
    expect(send).toBeDisabled()
  })

  it('keeps the conversations of an archived case but offers no way to write', async () => {
    page({ chat: true, write_chat: false })
    expect(await screen.findByText('Bring the call chart (fictional)')).toBeInTheDocument()
    expect(screen.queryByLabelText('Message')).toBeNull()
    expect(screen.getByText(/This case is archived: its conversations are kept/)).toBeInTheDocument()
  })

  it("is for the case's team only", async () => {
    page({ chat: false, write_chat: false })
    expect(await screen.findByText("Chat is for the case's team")).toBeInTheDocument()
    expect(kh.chatThreads).not.toHaveBeenCalled()
  })

  it('says what a message notice is about and leads to the right conversation', () => {
    const base = { id: 1, case_family_id: 'case-1', read_at: null, created_at: '2026-11-11T10:00:00Z' }
    const group = describeNotice({ ...base, kind: 'chat.message', payload: { by: 'SI Meera (fictional)', case: 'KH-2026-0009', case_id: 'c1', group: true, thread: 'group', preview: 'Bring the call chart' } } as never)
    expect(group.text).toBe('SI Meera (fictional) wrote to the team in KH-2026-0009: “Bring the call chart”')
    expect(group.href).toBe('/kh/case/c1/chat')
    const direct = describeNotice({ ...base, kind: 'chat.message', payload: { by: 'SI Meera (fictional)', case: 'KH-2026-0009', case_id: 'c1', group: false, thread: 'u-meera', preview: 'Call me' } } as never)
    expect(direct.text).toBe('SI Meera (fictional) wrote to you in KH-2026-0009: “Call me”')
    expect(direct.href).toBe('/kh/case/c1/chat?with=u-meera')
  })
})
