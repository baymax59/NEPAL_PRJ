import { render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MantineProvider } from '@mantine/core'
import { CdrAnalysisPage } from '../pages/CdrAnalysisPage'

vi.mock('../api/endpoints', () => ({
  getCdrSession: vi.fn(),
}))

import { getCdrSession } from '../api/endpoints'

const mockSession = {
  case_id: 'SC-2023-TEST',
  display_name: 'Test Analyst',
  role: 'analyst',
  msisdn_rule: 'in-msisdn.v1',
  timezone: 'Asia/Kolkata',
}

function renderCdrPage(displayId: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MantineProvider>
        <MemoryRouter initialEntries={[`/cases/${displayId}/cdr`]}>
          <Routes>
            <Route path="cases/:displayId/cdr" element={<CdrAnalysisPage />} />
          </Routes>
        </MemoryRouter>
      </MantineProvider>
    </QueryClientProvider>
  )
}

describe('CdrAnalysisPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows loader while fetching session', () => {
    vi.mocked(getCdrSession).mockReturnValue(new Promise(() => {}))
    renderCdrPage('SC-2023-TEST')
    expect(document.querySelector('.mantine-Loader-root')).toBeInTheDocument()
  })

  it('displays case ID badge after session loads', async () => {
    vi.mocked(getCdrSession).mockResolvedValue(mockSession)
    renderCdrPage('SC-2023-TEST')
    await waitFor(() => expect(screen.getByText('Case SC-2023-TEST')).toBeInTheDocument())
  })

  it('shows back link to host case page', async () => {
    vi.mocked(getCdrSession).mockResolvedValue(mockSession)
    renderCdrPage('SC-2023-TEST')
    await waitFor(() => {
      const backLink = screen.getByRole('link', { name: /back to case/i })
      expect(backLink).toHaveAttribute('href', '/cases/SC-2023-TEST')
    })
  })

  it('fetches session with the correct case_id', async () => {
    vi.mocked(getCdrSession).mockResolvedValue(mockSession)
    renderCdrPage('SC-2023-TEST')
    await waitFor(() => expect(getCdrSession).toHaveBeenCalledWith('SC-2023-TEST'))
  })

  it('shows error when session fetch fails (access denied)', async () => {
    vi.mocked(getCdrSession).mockRejectedValue(new Error('403: Case not accessible'))
    renderCdrPage('SC-2023-TEST')
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
  })

  it('renders all 15 canonical CDR tabs', async () => {
    vi.mocked(getCdrSession).mockResolvedValue(mockSession)
    renderCdrPage('SC-2023-TEST')
    await waitFor(() => {
      expect(screen.getByRole('tab', { name: /import.*evidence/i })).toBeInTheDocument()
      expect(screen.getByRole('tab', { name: /search.*analytics/i })).toBeInTheDocument()
      expect(screen.getByRole('tab', { name: /call graph/i })).toBeInTheDocument()
      expect(screen.getByRole('tab', { name: /audit trail/i })).toBeInTheDocument()
      expect(screen.getByRole('tab', { name: /chain of custody/i })).toBeInTheDocument()
      expect(screen.getByRole('tab', { name: /reports/i })).toBeInTheDocument()
    })
    // All 15 tabs must be present.
    const tabs = screen.getAllByRole('tab')
    expect(tabs.length).toBe(15)
  })

  it('shows DEV-ONLY authentication notice', async () => {
    vi.mocked(getCdrSession).mockResolvedValue(mockSession)
    renderCdrPage('SC-2023-TEST')
    await waitFor(() =>
      expect(screen.getByText(/DEV-ONLY authentication/i)).toBeInTheDocument()
    )
  })

  it('shows synthetic map notice', async () => {
    vi.mocked(getCdrSession).mockResolvedValue(mockSession)
    renderCdrPage('SC-2023-TEST')
    await waitFor(() =>
      expect(screen.getByText(/synthetic placeholder/i)).toBeInTheDocument()
    )
  })

  it('no credentials appear in any iframe src URL', async () => {
    vi.mocked(getCdrSession).mockResolvedValue(mockSession)
    renderCdrPage('SC-2023-TEST')
    await waitFor(() => expect(screen.getByText('Case SC-2023-TEST')).toBeInTheDocument())

    const iframes = document.querySelectorAll('iframe')
    for (const iframe of iframes) {
      const src = iframe.getAttribute('src') ?? ''
      expect(src).not.toMatch(/token=/i)
      expect(src).not.toMatch(/analyst.id=/i)
      expect(src).not.toMatch(/bearer/i)
    }
  })

  it('does not show standalone CDR case selector', async () => {
    vi.mocked(getCdrSession).mockResolvedValue(mockSession)
    renderCdrPage('SC-2023-TEST')
    await waitFor(() => expect(screen.queryByText(/select a case/i)).not.toBeInTheDocument())
  })
})
