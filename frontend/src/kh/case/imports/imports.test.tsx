// Imported findings: helpers and components. All data is fictional.

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders } from '../../../test/render'
import { kh } from '../../api'
import type { CaseDetail, ImportDetail, IndicatorsView as IndicatorsData, TestSourceView } from '../../types'
import { AddFromSourceDialog } from './AddFromSourceDialog'
import { linkReason, observedText, periodText } from './format'
import { ImportDrawer } from './ImportDrawer'
import { IndicatorsView } from './IndicatorsView'

vi.mock('../../api', () => ({
  kh: { importDetail: vi.fn(), indicators: vi.fn(), testSource: vi.fn(), sendTestFinding: vi.fn(), links: vi.fn(), addLink: vi.fn() },
  newKey: () => 'key',
}))

const CASE_REF = { id: 'case-1', display_id: 'KH-2026-0009', title: 'First fraud case (fictional)', case_type: 'cyber_fraud', priority: 'high', classification: 'restricted', workflow_status: 'open' }
const DETAIL = {
  ...CASE_REF,
  can: { add_files: true },
} as unknown as CaseDetail
const OTHER_CASE = {
  case: { id: 'case-2', display_id: 'KH-2026-0010', title: 'Second fraud case (fictional)', case_type: 'cyber_fraud', priority: 'high', classification: 'restricted', workflow_status: 'open' },
  imports: [{ display_id: 'IMP-0004', title: 'IPDR result', item_type: 'ipdr_result', item_type_label: 'IPDR analysis result', source: 'IPDR (fictional)', imported_at: '2026-11-07T10:00:00Z' }],
  linked: false,
}

function withQuery(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return renderWithProviders(<QueryClientProvider client={client}>{ui}</QueryClientProvider>)
}

describe('helpers', () => {
  it('show times as the source gave them, in their own timezone', () => {
    expect(observedText('2026-03-04T10:41:00+05:30')).toBe('4 Mar 2026, 10:41 (UTC+05:30)')
    expect(periodText('2026-03-03T09:58:00+05:30', '2026-03-03T11:20:00+05:30')).toBe('3 Mar 2026, 09:58 to 11:20 (UTC+05:30)')
    expect(observedText(null)).toBe('')
  })

  it('suggest a reason for linking that names the identifier and the findings', () => {
    expect(linkReason('Phone number', '+917000000042', ['IMP-0001'], ['IMP-0004'])).toBe(
      'The same phone number +917000000042 appears in imported findings of both cases (IMP-0001 here; IMP-0004 there).',
    )
  })
})

describe('ImportDrawer', () => {
  beforeEach(() => vi.mocked(kh.importDetail).mockReset())

  it('shows where the finding came from and offers to link a case that shares an identifier', async () => {
    vi.mocked(kh.importDetail).mockResolvedValue({
      case: CASE_REF, artifact_id: 'a1', display_id: 'IMP-0001', status: 'active', withdrawn_reason: null,
      title: 'Calls to the complainant (fictional)', version_number: 2, versions: 2, item_type: 'cdr_result', item_type_label: 'CDR analysis result',
      summary: 'FICTIONAL. Four calls on 3 March 2026.',
      source: { id: 's1', code: 'fict-cdr', name: 'CDR analysis (fictional)', kind: 'telecom', kind_label: 'CDR / IPDR analysis', fictional: false, status: 'enabled' },
      source_record_id: 'CDR-RES-01', source_hash: 'sha256:' + 'ab'.repeat(32), payload_ref: 'fict-cdr://analyses/01',
      authority_ref: 'Requisition FICT/017 (fictional)', observed_at: '2026-03-03T09:58:00+05:30', observed_until: null,
      identifiers: [{ type: 'phone', label: 'Phone number', value: '+917000000042', as_received: '070000 00042', in_this_case: [], other_cases: [OTHER_CASE] }],
      imported_by: { id: 'u1', username: 'inv.arun', display_name: 'SI Arun (fictional)' }, imported_at: '2026-11-07T10:00:00Z',
      received_with: 'khi_abcdefgh', content_sha256: 'd'.repeat(64), fictional: false,
      details: { calls: 4 },
      history: [
        { version_number: 1, source_hash: 'sha256:' + '11'.repeat(32), change_note: null, imported_by: null, imported_at: '2026-11-06T10:00:00Z', received_with: 'khi_abcdefgh', content_sha256: 'f'.repeat(64), current: false },
        { version_number: 2, source_hash: 'sha256:' + 'ab'.repeat(32), change_note: "Updated in CDR analysis (fictional): the record's hash changed", imported_by: null, imported_at: '2026-11-07T10:00:00Z', received_with: 'khi_abcdefgh', content_sha256: 'd'.repeat(64), current: true },
      ],
      used_by: [], policy_note: 'Raw data stays in the source system.',
    } as ImportDetail)
    vi.mocked(kh.links).mockResolvedValue({ link_types: [{ code: 'shared_evidence', label: 'Shared evidence or indicator' }] } as never)
    withQuery(<ImportDrawer detail={DETAIL} artifactId="a1" onClose={() => {}} />)
    expect(await screen.findByText('Calls to the complainant (fictional)')).toBeInTheDocument()
    expect(screen.getByText('Requisition FICT/017 (fictional)')).toBeInTheDocument()
    expect(screen.getByText('CDR-RES-01')).toBeInTheDocument()
    expect(screen.getByText('received as "070000 00042"')).toBeInTheDocument()
    expect(screen.getByText('Versions: each time the source changed its record')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Link KH-2026-0010' }))
    expect(await screen.findByDisplayValue(/The same phone number \+917000000042 appears/)).toBeInTheDocument()
  })
})

describe('IndicatorsView', () => {
  it('lists identifiers with the other cases where they appear', async () => {
    vi.mocked(kh.indicators).mockResolvedValue({
      case: CASE_REF,
      indicators: [
        { type: 'phone', label: 'Phone number', value: '+917000000042', imports: [{ artifact_id: 'a1', display_id: 'IMP-0001', status: 'active', item_type_label: 'CDR analysis result' }], other_cases: [{ ...OTHER_CASE, linked: true }] },
        { type: 'ip', label: 'IP address', value: '203.0.113.45', imports: [{ artifact_id: 'a2', display_id: 'IMP-0002', status: 'active', item_type_label: 'Log event' }], other_cases: [] },
      ],
      totals: { identifiers: 2, with_matches: 1, cases: 1 },
      note: 'Matches are shown only in cases you can open.',
    } as IndicatorsData)
    const open = vi.fn()
    withQuery(<IndicatorsView detail={DETAIL} onOpen={open} />)
    expect(await screen.findByText('+917000000042')).toBeInTheDocument()
    expect(screen.getByText('KH-2026-0010')).toBeInTheDocument()
    expect(screen.getByText('linked')).toBeInTheDocument()
    expect(screen.getByText('None that you can open')).toBeInTheDocument()
    await userEvent.click(screen.getByText('IMP-0002'))
    expect(open).toHaveBeenCalledWith('a2')
  })
})

describe('AddFromSourceDialog', () => {
  const view = (registered: boolean): TestSourceView => ({
    registered,
    source: null,
    note: 'FICTIONAL TEST SOURCE.',
    findings: [
      { id: 'log-new-device-login', system: 'Log Analyzer (fictional)', item_type: 'log_event', item_type_label: 'Log event', source_record_id: 'LA-EVT-1', title: 'New-device login', summary: 'FICTIONAL.', payload_ref: null, authority_ref: null, observed_at: '2026-03-04T10:41:00+05:30', observed_until: null, identifiers: [], details: {}, source_hash: 'sha256:' + '0'.repeat(64) },
    ],
  })

  it('says an administrator must register the test source first', async () => {
    vi.mocked(kh.testSource).mockResolvedValue(view(false))
    withQuery(<AddFromSourceDialog detail={DETAIL} onClose={() => {}} />)
    expect(await screen.findByText(/first registers the fictional test source/)).toBeInTheDocument()
  })

  it('adds a fictional finding straight into the case', async () => {
    vi.mocked(kh.testSource).mockResolvedValue(view(true))
    vi.mocked(kh.sendTestFinding).mockResolvedValue({ entry: 5, finding: { display_id: 'IMP-0001', version_number: 1 }, updated: false } as never)
    withQuery(<AddFromSourceDialog detail={DETAIL} onClose={() => {}} />)
    await userEvent.click(await screen.findByRole('button', { name: 'Add LA-EVT-1 to the case' }))
    expect(vi.mocked(kh.sendTestFinding)).toHaveBeenCalledWith({ finding_id: 'log-new-device-login', case_id: 'case-1' }, 'key')
    expect(await screen.findByText('added as IMP-0001')).toBeInTheDocument()
  })
})
