// Case overview: the folders, the description, recent activity, and the facts, status and references at a glance.

import { Anchor, Autocomplete, Badge, Button, Grid, Group, Modal, Paper, Select, SimpleGrid, Stack, Table, Text, TextInput, Textarea, Timeline } from '@mantine/core'
import { IconArrowsExchange, IconFolder, IconLock, IconPlus, IconShieldCheck } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router'
import { kh } from '../api'
import { ContentView } from '../content'
import { toastDone, toastError, useOnceKey } from '../feedback'
import { humanize, roleLabel, SUPERVISOR_DECISIONS, WORKFLOW_NEXT, workflowLook } from '../labels'
import { CaseGovernancePanel } from '../pages/CaseGovernancePanel'
import { RichTextView } from '../RichText'
import { formatDay, formatWhen } from '../time'
import type { CaseDetail } from '../types'
import { EmptyState, EntryBadge, EntryNumber, Facts, Loaded, Panel, PersonName, When } from '../ui'
import { useCase } from './context'
import { HandOverDialog } from './dialogs'

function ReportedBy({ who }: { who: CaseDetail['reported_by'] }) {
  if (!who) return <Text size="sm">not recorded</Text>
  if (who.unknown) return <Text size="sm">Unknown</Text>
  const contact = [who.phone, who.email].filter(Boolean).join(' · ')
  return (
    <Stack gap={0}>
      {who.name && <Text size="sm">{who.name}</Text>}
      {contact && (
        <Text size="xs" c="dimmed">
          {contact}
        </Text>
      )}
      {who.address && (
        <Text size="xs" c="dimmed">
          {who.address}
        </Text>
      )}
    </Stack>
  )
}

export function OverviewTab() {
  const detail = useCase()
  const [dialog, setDialog] = useState<null | 'workflow' | 'official' | 'reference' | 'handover'>(null)
  const recent = useQuery({ queryKey: ['kh', 'case', detail.id, 'history', 'recent'], queryFn: () => kh.history(detail.id, { latest: 6 }) })
  const base = `/kh/case/${detail.id}`

  return (
    <Grid gap="md">
      <Grid.Col span={{ base: 12, md: 8 }}>
        <Stack gap="md">
          <Panel title="Folders" p="0">
            {detail.folders.length === 0 ? (
              <EmptyState title="No folders yet" />
            ) : (
              <Table>
                <Table.Tbody>
                  {detail.folders.map((folder) => (
                    <Table.Tr key={folder.id}>
                      <Table.Td>
                        <Group gap={8} wrap="nowrap">
                          <IconFolder size={16} color="var(--mantine-color-hawk-4)" />
                          <Anchor component={Link} to={`${base}/files?folder=${encodeURIComponent(folder.name)}`} size="sm">
                            {folder.name}
                          </Anchor>
                          {folder.system && (
                            <Badge size="xs" variant="outline" color="gray">
                              made by the system
                            </Badge>
                          )}
                        </Group>
                      </Table.Td>
                      <Table.Td>
                        <Text size="xs" c="dimmed">
                          {folder.files === 0 ? 'empty' : `${folder.files} ${folder.files === 1 ? 'file' : 'files'}`}
                        </Text>
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            )}
          </Panel>

          <Panel title="Case description">
            <Stack gap="xs">
              {detail.description_html ? <RichTextView html={detail.description_html} /> : <ContentView content={{ text: detail.description }} />}
              {detail.jurisdiction && (
                <Text size="xs" c="dimmed">
                  Jurisdiction: {detail.jurisdiction}
                </Text>
              )}
            </Stack>
          </Panel>

          <Panel title="Recent activity" actions={<Anchor component={Link} to={`${base}/history`} size="xs">Whole history</Anchor>}>
            <Loaded query={recent}>
              {(view) => (
                <Stack gap={6}>
                  {[...view.entries].reverse().map((entry) => (
                    <Group key={entry.seq} gap="xs" wrap="nowrap" justify="space-between">
                      <Group gap="xs" wrap="nowrap" style={{ minWidth: 0 }}>
                        <EntryBadge value={entry.kind} />
                        <Text size="sm" truncate>
                          {entry.summary}
                        </Text>
                      </Group>
                      <Group gap="xs" wrap="nowrap">
                        <PersonName person={entry.actor} size="xs" />
                        <EntryNumber seq={entry.seq} caseId={detail.id} />
                        <When at={entry.at} size="xs" />
                      </Group>
                    </Group>
                  ))}
                </Stack>
              )}
            </Loaded>
          </Panel>
        </Stack>
      </Grid.Col>

      <Grid.Col span={{ base: 12, md: 4 }}>
        <Stack gap="md">
          <Panel title="About">
            <Facts
              cols={1}
              items={[
                ['Type of case', detail.case_type_label],
                ['Official status', detail.official_status ?? 'not recorded'],
                ['Supervisor', <PersonName key="s" person={detail.supervisor} size="xs" />],
                ['Reported by', <ReportedBy key="r" who={detail.reported_by} />],
                ['Registered', `${formatWhen(detail.created_at)}${detail.created_by ? ` by ${detail.created_by.display_name}` : ''}`],
              ]}
            />
            <Group gap="xs" mt="sm">
              {detail.can.change_workflow_status && (
                <Button size="xs" variant="light" onClick={() => setDialog('workflow')}>
                  Change case status
                </Button>
              )}
              {detail.can.change_official_status && (
                <Button size="xs" variant="default" onClick={() => setDialog('official')}>
                  Record official status
                </Button>
              )}
              {detail.can.hand_over && (
                <Button size="xs" variant="default" leftSection={<IconArrowsExchange size={14} />} onClick={() => setDialog('handover')}>
                  Hand over the case
                </Button>
              )}
            </Group>
          </Panel>

          <Panel
            title="Official references"
            actions={
              detail.can.add_official_reference && (
                <Button size="compact-xs" variant="subtle" leftSection={<IconPlus size={12} />} onClick={() => setDialog('reference')}>
                  Add
                </Button>
              )
            }
          >
            {detail.references.length === 0 ? (
              <Text size="sm" c="dimmed">
                None recorded.
              </Text>
            ) : (
              <Stack gap={6}>
                {detail.references.map((r) => (
                  <div key={r.id}>
                    <Text size="sm" fw={500}>
                      {r.ref_type} {r.number}
                    </Text>
                    <Text size="xs" c="dimmed">
                      {[r.issuing_authority, r.ref_date ? formatDay(r.ref_date) : null, `recorded ${formatDay(r.recorded_at)} by ${r.recorded_by?.display_name ?? '—'}`].filter(Boolean).join(' · ')}
                    </Text>
                  </div>
                ))}
              </Stack>
            )}
          </Panel>

          <Panel title="Work in progress">
            <Stack gap={6}>
              <Group justify="space-between">
                <Anchor component={Link} to={`${base}/files`} size="sm">
                  Files
                </Anchor>
                <Badge color="gray">{detail.folders.reduce((total, f) => total + f.files, 0)}</Badge>
              </Group>
            </Stack>
          </Panel>

          <Panel title="Team" actions={<Anchor component={Link} to={`${base}/team`} size="xs">{detail.can.manage_team ? 'Manage' : 'See all'}</Anchor>}>
            <Stack gap={6}>
              {detail.team
                .filter((m) => !m.revoked_at)
                .map((m) => (
                  <Group key={m.user?.id} justify="space-between" wrap="nowrap">
                    <PersonName person={m.user} size="xs" />
                    <Text size="xs" c="dimmed">
                      {roleLabel(m.role)}
                    </Text>
                  </Group>
                ))}
            </Stack>
          </Panel>

          <CaseGovernancePanel caseId={detail.id} />

          <Panel title="Status history (permanent)">
            {detail.status_history.length === 0 ? (
              <Text size="sm" c="dimmed">
                No changes yet.
              </Text>
            ) : (
              <Timeline bulletSize={12} lineWidth={2}>
                {detail.status_history.map((e, i) => (
                  <Timeline.Item key={i}>
                    <Text size="xs">
                      <b>{humanize(e.field)}</b>: {e.field === 'workflow' ? `${workflowLook(e.old_value).label} → ${workflowLook(e.new_value).label}` : `${e.old_value ?? '—'} → ${e.new_value}`}
                    </Text>
                    <Text size="xs" c="dimmed">
                      {formatWhen(e.at)} · {e.actor?.display_name ?? '—'}
                      {e.reason ? ` · “${e.reason}”` : ''}
                    </Text>
                  </Timeline.Item>
                ))}
              </Timeline>
            )}
          </Panel>

          <Paper withBorder p="sm" radius="sm">
            <Group gap="xs" wrap="nowrap" align="flex-start">
              <IconShieldCheck size={18} color="var(--mantine-color-green-5)" style={{ flex: 'none', marginTop: 2 }} />
              <Text size="xs" c="dimmed">
                Everything that happens in the case is written into its numbered history, and every exhibit is checked automatically. Nothing here can be deleted:
                a mistake is corrected with a new version, or the wrong file is withdrawn with a reason.
              </Text>
            </Group>
            {detail.workflow_status === 'archived' && (
              <Group gap="xs" wrap="nowrap" align="flex-start" mt="xs">
                <IconLock size={18} style={{ flex: 'none', marginTop: 2 }} />
                <Text size="xs" c="dimmed">This case is archived: it is read-only.</Text>
              </Group>
            )}
          </Paper>
        </Stack>
      </Grid.Col>
      {dialog === 'workflow' && <StatusDialog detail={detail} field="workflow" onClose={() => setDialog(null)} />}
      {dialog === 'official' && <StatusDialog detail={detail} field="official" onClose={() => setDialog(null)} />}
      {dialog === 'reference' && <ReferenceDialog detail={detail} onClose={() => setDialog(null)} />}
      {dialog === 'handover' && <HandOverDialog opened onClose={() => setDialog(null)} detail={detail} />}
    </Grid>
  )
}

function StatusDialog({ detail, field, onClose }: { detail: CaseDetail; field: 'workflow' | 'official'; onClose: () => void }) {
  const queryClient = useQueryClient()
  const next = WORKFLOW_NEXT[detail.workflow_status] ?? []
  const [value, setValue] = useState<string | null>(field === 'workflow' ? (next[0] ?? null) : '')
  const [reason, setReason] = useState('')
  const mutation = useMutation({
    mutationFn: () => kh.changeCaseStatus(detail.id, { field, value: (value ?? '').trim(), reason: reason.trim() }),
    onSuccess: () => {
      toastDone('Status changed and recorded')
      queryClient.invalidateQueries({ queryKey: ['kh'] })
      onClose()
    },
    onError: (error) => toastError(error, 'Not changed'),
  })
  return (
    <Modal opened onClose={onClose} title={<Text fw={600}>{field === 'workflow' ? 'Change the case status' : 'Record the official status'}</Text>}>
      <Stack gap="sm">
        {field === 'workflow' ? (
          <>
            <Text size="sm">
              Now: <b>{workflowLook(detail.workflow_status).label}</b>
            </Text>
            <Select
              label="New status"
              data={next.map((s) => ({ value: s, label: `${workflowLook(s).label}${SUPERVISOR_DECISIONS.includes(s) ? ' (supervisor)' : ''}` }))}
              value={value}
              onChange={setValue}
              allowDeselect={false}
            />
            <Text size="xs" c="dimmed">
              The internal workflow status is separate from the official police status: closing the investigation here doesn't close the official case.
            </Text>
          </>
        ) : (
          <TextInput label="Official status, as written in the official record" value={value ?? ''} onChange={(e) => setValue(e.currentTarget.value)} maxLength={64} />
        )}
        <Textarea label="Reason (kept in the history)" value={reason} onChange={(e) => setReason(e.currentTarget.value)} autosize minRows={2} required />
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={!value?.trim() || reason.trim().length < 5} loading={mutation.isPending} onClick={() => mutation.mutate()}>
            Change
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}

function ReferenceDialog({ detail, onClose }: { detail: CaseDetail; onClose: () => void }) {
  const queryClient = useQueryClient()
  const [key, renew] = useOnceKey()
  const [refType, setRefType] = useState('FIR')
  const [number, setNumber] = useState('')
  const [authority, setAuthority] = useState('')
  const [date, setDate] = useState('')
  const [source, setSource] = useState('manual')
  const mutation = useMutation({
    mutationFn: () => kh.addReference(detail.id, { ref_type: refType.trim(), number: number.trim(), issuing_authority: authority.trim() || null, ref_date: date || null, source: source.trim() || 'manual' }, key),
    onSuccess: () => {
      renew()
      toastDone('Reference recorded')
      queryClient.invalidateQueries({ queryKey: ['kh', 'case', detail.id] })
      onClose()
    },
    onError: (error) => toastError(error, 'Not recorded'),
  })
  return (
    <Modal opened onClose={onClose} title={<Text fw={600}>Add an official reference</Text>}>
      <Stack gap="sm">
        <SimpleGrid cols={2}>
          <Autocomplete label="Kind" data={['FIR', 'Complaint', 'General diary entry', 'Court case', 'Notice', 'Other']} value={refType} onChange={setRefType} />
          <TextInput label="Number" value={number} onChange={(e) => setNumber(e.currentTarget.value)} required />
          <TextInput label="Issued by" value={authority} onChange={(e) => setAuthority(e.currentTarget.value)} />
          <TextInput label="Date" type="date" value={date} onChange={(e) => setDate(e.currentTarget.value)} />
        </SimpleGrid>
        <TextInput label="Source" description="Where the reference comes from (e.g. manual entry, the FIR register)." value={source} onChange={(e) => setSource(e.currentTarget.value)} />
        <Paper withBorder p="xs" bg="var(--mantine-color-default-hover)">
          <Text size="xs" c="dimmed">
            References are permanent: a wrong one stays, and the correct one is added next to it.
          </Text>
        </Paper>
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={!refType.trim() || !number.trim()} loading={mutation.isPending} onClick={() => mutation.mutate()}>
            Record
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}
