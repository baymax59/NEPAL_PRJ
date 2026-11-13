// Signed PDF reports: generated from the case as it stands, kept write-once as versions of one report file, downloaded
// through one-time links, and checked at any time (a changed file fails the check).

import { Alert, Anchor, Badge, Button, Group, Modal, Paper, SegmentedControl, Stack, Table, Text, Textarea } from '@mantine/core'
import { IconDownload, IconFileCertificate, IconShieldCheck } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router'
import { formatBytes } from '../../lib/format'
import { kh } from '../api'
import { toastDone, toastError, useOnceKey } from '../feedback'
import type { CaseDetail, ReportVersion } from '../types'
import { EntryNumber, Loaded, PersonName, When } from '../ui'

const TYPES = [
  { value: 'case_report', label: 'Case report' },
  { value: 'evidence_register', label: 'Evidence register' },
]

export function CheckBadge({ result }: { result?: string | null }) {
  if (!result) return <Badge color="gray" variant="light" size="sm">not checked yet</Badge>
  const look: Record<string, [string, string]> = {
    match: ['teal', 'intact'],
    mismatch: ['red', 'changed'],
    missing: ['red', 'missing'],
    unknown: ['orange', 'not recognised'],
  }
  const [color, label] = look[result] ?? ['gray', result]
  return (
    <Badge color={color} variant="light" size="sm">
      {label}
    </Badge>
  )
}

export function SignedReports({ detail }: { detail: CaseDetail }) {
  const client = useQueryClient()
  const query = useQuery({ queryKey: ['kh', 'case', detail.id, 'reports'], queryFn: () => kh.reports(detail.id) })
  const [generating, setGenerating] = useState(false)
  const verify = useMutation({
    mutationFn: (id: string) => kh.verifyReport(id),
    onSuccess: (check) => {
      client.invalidateQueries({ queryKey: ['kh', 'case', detail.id, 'reports'] })
      if (check.result === 'match') toastDone(check.message)
      else toastError(new Error(check.message), 'The report failed its check')
    },
    onError: (error) => toastError(error, 'Not checked'),
  })
  const download = useMutation({
    mutationFn: (id: string) => kh.reportDownloadLink(id),
    onSuccess: (link) => {
      window.location.assign(link.url)
      // The download re-hashes the stored copy first: show that check once it is recorded.
      window.setTimeout(() => client.invalidateQueries({ queryKey: ['kh', 'case', detail.id, 'reports'] }), 1500)
    },
    onError: (error) => toastError(error, 'No download'),
  })
  return (
    <Paper withBorder p="md" radius="sm" className="no-print">
      <Group justify="space-between" mb="xs" wrap="wrap">
        <Group gap="xs">
          <IconFileCertificate size={18} />
          <Text fw={600}>Signed reports</Text>
        </Group>
        <Group gap="xs">
          <Anchor component={Link} to="/kh/verify-report" size="sm">
            Check a report file
          </Anchor>
          {detail.can.add_files && (
            <Button size="xs" leftSection={<IconFileCertificate size={14} />} onClick={() => setGenerating(true)}>
              Generate a signed PDF
            </Button>
          )}
        </Group>
      </Group>
      <Text size="xs" c="dimmed" mb="sm">
        A signed report is a PDF of the case as it stood at one entry of its history, with only what every member of the case may see. It is recorded and the file is kept
        write-once, so anyone holding a copy can check that it is exactly the one generated. It is not automatically admissible in court.
      </Text>
      <Loaded query={query}>
        {(data) =>
          data.reports.length === 0 ? (
            <Text size="sm" c="dimmed">
              No signed report yet.
            </Text>
          ) : (
            <Table.ScrollContainer minWidth={760}>
              <Table verticalSpacing="xs" fz="sm">
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Report</Table.Th>
                    <Table.Th>Describes</Table.Th>
                    <Table.Th>Generated</Table.Th>
                    <Table.Th>Latest check</Table.Th>
                    <Table.Th />
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {data.reports.map((r) => (
                    <ReportRow
                      key={r.id}
                      report={r}
                      caseId={detail.id}
                      onVerify={() => verify.mutate(r.id)}
                      onDownload={() => download.mutate(r.id)}
                      busy={verify.isPending || download.isPending}
                    />
                  ))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
          )
        }
      </Loaded>
      {generating && <GenerateDialog detail={detail} onClose={() => setGenerating(false)} />}
    </Paper>
  )
}

function ReportRow({ report: r, caseId, onVerify, onDownload, busy }: { report: ReportVersion; caseId: string; onVerify: () => void; onDownload: () => void; busy: boolean }) {
  return (
    <Table.Tr>
      <Table.Td>
        <Text size="sm" fw={600}>
          {r.display_id} · version {r.version_number}
        </Text>
        <Text size="xs" c="dimmed">
          {r.title} · {r.page_count} page{r.page_count === 1 ? '' : 's'} · {formatBytes(r.size_bytes)}
          {r.withheld_entries ? ` · ${r.withheld_entries} withheld` : ''}
        </Text>
        <Text size="xs" c="dimmed" lineClamp={2}>
          {r.purpose}
        </Text>
      </Table.Td>
      <Table.Td>
        <Text size="xs">as of</Text>
        <EntryNumber seq={r.as_of_entry} caseId={caseId} />
      </Table.Td>
      <Table.Td>
        <Stack gap={2}>
          <PersonName person={r.generated_by} size="xs" />
          <When at={r.generated_at} size="xs" />
        </Stack>
      </Table.Td>
      <Table.Td>
        <CheckBadge result={r.last_check?.result} />
      </Table.Td>
      <Table.Td>
        <Group gap={4} wrap="nowrap" justify="flex-end">
          <Button size="compact-xs" variant="light" leftSection={<IconDownload size={13} />} onClick={onDownload} disabled={busy} aria-label={`Download ${r.display_id} version ${r.version_number}`}>
            PDF
          </Button>
          <Button size="compact-xs" variant="default" leftSection={<IconShieldCheck size={13} />} onClick={onVerify} disabled={busy} aria-label={`Check ${r.display_id} version ${r.version_number}`}>
            Check
          </Button>
        </Group>
      </Table.Td>
    </Table.Tr>
  )
}

function GenerateDialog({ detail, onClose }: { detail: CaseDetail; onClose: () => void }) {
  const client = useQueryClient()
  const [key, renew] = useOnceKey()
  const [type, setType] = useState('case_report')
  const [purpose, setPurpose] = useState('')
  const generate = useMutation({
    mutationFn: () => kh.generateReport(detail.id, { report_type: type as 'case_report', purpose: purpose.trim() }, key),
    onSuccess: (made) => {
      renew()
      client.invalidateQueries({ queryKey: ['kh', 'case', detail.id] })
      toastDone(`${made.report.display_id} version ${made.report.version_number} generated, as of entry ${made.report.as_of_entry}`)
      onClose()
    },
    onError: (error) => toastError(error, 'No report generated'),
  })
  return (
    <Modal opened onClose={onClose} size="lg" title={<Text fw={600}>Generate a signed PDF report</Text>}>
      <Stack gap="sm">
        <SegmentedControl data={TYPES} value={type} onChange={setType} />
        <Text size="xs" c="dimmed">
          {type === 'case_report'
            ? 'The whole case as it stands now: exhibits with their integrity checks, notes and analyses, imported findings, the timeline and the team.'
            : 'The exhibits only, with their custodians, integrity checks and full chain of custody.'}
        </Text>
        <Textarea
          label="Purpose"
          description="What the report is for (10 to 500 characters). It is printed in the report."
          value={purpose}
          onChange={(e) => setPurpose(e.currentTarget.value)}
          autosize
          minRows={2}
          maxLength={500}
          required
        />
        <Alert color="blue" variant="light" p="xs">
          <Text size="xs">
            The report contains only what every member of the case may see: sealed exhibits and notes are left out, and counted. Each report is a new
            version of the same report file; earlier versions stay.
          </Text>
        </Alert>
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button loading={generate.isPending} disabled={purpose.trim().length < 10} onClick={() => generate.mutate()}>
            Generate
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}
