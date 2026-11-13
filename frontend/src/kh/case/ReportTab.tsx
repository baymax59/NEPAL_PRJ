// Reports (spec §21 screen 19, §22): signed, versioned PDF reports that can be checked later, and a printable preview of the
// case as it stands now, with provenance and integrity information, as you may see it.

import { Alert, Box, Button, Divider, Group, Paper, SimpleGrid, Stack, Table, Text, Title } from '@mantine/core'
import { IconAlertTriangle, IconPrinter, IconShieldCheck } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { formatBytes } from '../../lib/format'
import { kh } from '../api'
import { HawkMark } from '../Brand'
import { ARTIFACT_TYPES, classificationLook, humanize, integrityLook, roleLabel, workflowLook } from '../labels'
import { formatWhen } from '../time'
import { Loaded } from '../ui'
import { useCase } from './context'
import { SignedReports } from './SignedReports'

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Box mt="lg" style={{ breakInside: 'avoid-page' }}>
      <Title order={4} size="h5" mb={6} tt="uppercase" style={{ letterSpacing: 0.6 }}>
        {title}
      </Title>
      {children}
    </Box>
  )
}

export function ReportTab() {
  const detail = useCase()
  const query = useQuery({ queryKey: ['kh', 'case', detail.id, 'report-preview'], queryFn: () => kh.reportPreview(detail.id) })
  return (
    <Stack gap="sm">
      <Group justify="space-between" className="no-print">
        <Text size="xs" c="dimmed">
          The preview shows the case as it stands now, as you may see it. A signed report records the entry of the history it describes.
        </Text>
        <Button size="xs" variant="default" leftSection={<IconPrinter size={14} />} onClick={() => window.print()} disabled={!query.data}>
          Print this preview
        </Button>
      </Group>
      <SignedReports detail={detail} />
      <Loaded query={query}>
        {(r) => (
          <Paper withBorder p="xl" radius="sm" className="kh-report">
            <Group justify="space-between" align="flex-start">
              <Group gap="sm">
                <HawkMark size={34} />
                <div>
                  <Text fw={800} style={{ letterSpacing: 1.2 }}>
                    KNIGHT HAWK · CASE REPORT
                  </Text>
                  <Text size="xs" c="dimmed">
                    Preview generated {formatWhen(r.generated_at)} by {r.generated_by?.display_name ?? '—'}
                  </Text>
                </div>
              </Group>
              <Stack gap={0} align="flex-end">
                <Text ff="monospace" fw={700}>
                  {r.case.display_id}
                </Text>
                <Text size="xs" c="dimmed">
                  {classificationLook(r.case.classification).label.toUpperCase()}
                </Text>
              </Stack>
            </Group>
            <Alert color="yellow" variant="light" icon={<IconAlertTriangle size={16} />} mt="md" p="xs">
              <Text size="xs">{r.preview_note}</Text>
            </Alert>

            <Section title="Case">
              <Title order={3} size="h4">
                {r.case.title}
              </Title>
              <SimpleGrid cols={{ base: 1, sm: 3 }} mt="xs" spacing="xs">
                <Fact label="Case number" value={r.case.display_id} />
                <Fact label="Official references" value={r.case.references.join(', ') || 'none recorded'} />
                <Fact label="Case status" value={workflowLook(r.case.workflow_status).label} />
                <Fact label="Official status" value={r.case.official_status ?? '—'} />
                <Fact label="Priority" value={humanize(r.case.priority)} />
                <Fact label="Jurisdiction" value={r.case.jurisdiction ?? '—'} />
              </SimpleGrid>
              <Text size="sm" mt="xs" style={{ whiteSpace: 'pre-wrap' }}>
                {r.case.description}
              </Text>
            </Section>

            <Section title="State of the case described">
              <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="xs">
                <Fact label="As of" value={`entry ${r.history.entries} of the history`} />
                <Fact label="History check" value={r.history.intact ? 'The history is intact' : 'FAILED: the history no longer checks out'} />
                <Fact label="Folders" value={r.folders.join(', ') || '—'} />
              </SimpleGrid>
            </Section>

            <Section title="Integrity summary">
              <Group gap="lg">
                <Group gap={6}>
                  <IconShieldCheck size={16} color="var(--mantine-color-green-6)" />
                  <Text size="sm">{r.integrity.match} intact</Text>
                </Group>
                <Text size="sm" c={r.integrity.mismatch + r.integrity.missing ? 'red' : undefined}>
                  {r.integrity.mismatch} changed · {r.integrity.missing} missing
                </Text>
                <Text size="sm" c={r.integrity.never_checked ? 'yellow' : undefined}>
                  {r.integrity.never_checked} not checked yet
                </Text>
              </Group>
              {r.withheld_entries > 0 && (
                <Text size="xs" c="dimmed" mt={4}>
                  {r.withheld_entries} sealed {r.withheld_entries === 1 ? 'file is' : 'files are'} left out: you may not see {r.withheld_entries === 1 ? 'it' : 'them'}.
                </Text>
              )}
            </Section>

            <Section title={`Exhibits (${r.evidence.length})`}>
              {r.evidence.length === 0 ? (
                <Text size="sm" c="dimmed">
                  No exhibits yet.
                </Text>
              ) : (
                <Table withTableBorder fz="xs" verticalSpacing={4}>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Exhibit</Table.Th>
                      <Table.Th>File</Table.Th>
                      <Table.Th>Collected</Table.Th>
                      <Table.Th>Custody</Table.Th>
                      <Table.Th>Latest integrity check</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {r.evidence.map((e) => (
                      <Table.Tr key={e.display_id}>
                        <Table.Td>
                          <b>{e.display_id}</b> {e.title}
                          <div>
                            {humanize(e.evidence_type)} · folder {e.folder}
                          </div>
                          {e.status === 'withdrawn' && <div>Withdrawn: {e.withdrawn_reason}</div>}
                        </Table.Td>
                        <Table.Td>
                          <div>
                            {e.original_filename} · {e.mime_type} · {e.size_bytes ? formatBytes(e.size_bytes) : ''}
                          </div>
                        </Table.Td>
                        <Table.Td>
                          {e.collected_at ? formatWhen(e.collected_at) : '—'}
                          {e.collected_by && <div>by {e.collected_by}</div>}
                          {e.collection_authority && <div>{e.collection_authority}</div>}
                          {e.source && <div>Source: {e.source}</div>}
                        </Table.Td>
                        <Table.Td>
                          {e.custodian ? (e.custodian.user?.display_name ?? e.custodian.name) : '—'}
                          {e.transfer_pending && <div>handover pending</div>}
                        </Table.Td>
                        <Table.Td>{e.last_check ? `${integrityLook(e.last_check.result).label}, ${formatWhen(e.last_check.checked_at)}` : 'Not checked yet'}</Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              )}
            </Section>

            <Section title={`Notes and analyses (${r.artifacts.length})`}>
              <Table withTableBorder fz="xs" verticalSpacing={4}>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Note</Table.Th>
                    <Table.Th>Kind</Table.Th>
                    <Table.Th>Version</Table.Th>
                    <Table.Th>Author</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {r.artifacts.map((a) => (
                    <Table.Tr key={a.display_id}>
                      <Table.Td>
                        <b>{a.display_id}</b> {a.title}
                        <div>folder {a.folder}</div>
                        {a.status === 'withdrawn' && <div>Withdrawn: {a.withdrawn_reason}</div>}
                      </Table.Td>
                      <Table.Td>{ARTIFACT_TYPES[a.artifact_type] ?? humanize(a.artifact_type)}</Table.Td>
                      <Table.Td>
                        version {a.version_number} · {formatWhen(a.version_created_at)}
                      </Table.Td>
                      <Table.Td>{a.author?.display_name ?? '—'}</Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Section>

            {(r.imports ?? []).length > 0 && (
              <Section title={`Findings imported from other systems (${(r.imports ?? []).length})`}>
                <Table withTableBorder fz="xs" verticalSpacing={4}>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Finding</Table.Th>
                      <Table.Th>Source and record</Table.Th>
                      <Table.Th>Legal authority</Table.Th>
                      <Table.Th>Added</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {(r.imports ?? []).map((f, i) => (
                      <Table.Tr key={f.display_id ?? i}>
                        <Table.Td>
                          <b>{f.display_id}</b> {f.title} {f.fictional ? '(fictional test data)' : ''}
                          <div>
                            {humanize(f.item_type)}
                            {f.observed_at ? `, happened ${f.observed_at.replace('T', ' ')}` : ''}
                          </div>
                          {f.status === 'withdrawn' && <div>Withdrawn from the case</div>}
                        </Table.Td>
                        <Table.Td>
                          {f.source ?? '—'}, record {f.source_record_id}
                        </Table.Td>
                        <Table.Td>{f.authority_ref ?? 'Not required by the source’s policy'}</Table.Td>
                        <Table.Td>
                          for {f.imported_by?.display_name ?? '—'} {f.imported_at ? `on ${formatWhen(f.imported_at)}` : ''}
                        </Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </Section>
            )}

            <Section title="Team">
              <Table withTableBorder fz="xs" verticalSpacing={4}>
                <Table.Tbody>
                  {r.team.map((m, i) => (
                    <Table.Tr key={i}>
                      <Table.Td>{m.user?.display_name ?? '—'}</Table.Td>
                      <Table.Td>{roleLabel(m.role)}</Table.Td>
                      <Table.Td>
                        from {formatWhen(m.granted_at)}
                        {m.revoked_at ? ` to ${formatWhen(m.revoked_at)}` : ''}
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Section>

            <Divider my="lg" />
            <Text size="xs" fw={600}>
              Important
            </Text>
            <Text size="xs">{r.disclaimer}</Text>
          </Paper>
        )}
      </Loaded>
    </Stack>
  )
}

function Fact({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <Box>
      <Text size="10px" c="dimmed" tt="uppercase" fw={600}>
        {label}
      </Text>
      <Text size="sm" component="div">
        {value}
      </Text>
    </Box>
  )
}
