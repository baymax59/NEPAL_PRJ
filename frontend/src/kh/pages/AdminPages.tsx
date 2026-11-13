// The administrator's portal (spec §14): the whole organisation's cases, their history, evidence integrity and activity.
// There are no delete controls anywhere: nothing in Knight Hawk is deleted.

import { Alert, Anchor, Badge, Button, Grid, Group, Paper, Select, SimpleGrid, Stack, Table, Tabs, Text, TextInput, ThemeIcon, Timeline } from '@mantine/core'
import { BarChart } from '@mantine/charts'
import { useDebouncedValue } from '@mantine/hooks'
import { IconAlertTriangle, IconQuestionMark, IconSearch, IconShieldCheck, IconShieldX } from '@tabler/icons-react'
import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { formatBytes } from '../../lib/format'
import { kh } from '../api'
import { ChartPanel, CHART_SERIES } from '../charts'
import { CaseAuditTrail } from '../case/AuditTab'
import { roleLabel, WORKFLOW_STATUSES, workflowLook } from '../labels'
import { EmptyState, EntryBadge, IntegrityBadge, Loaded, PageHeader, Panel, PersonName, PriorityBadge, Stat, When, WorkflowBadge } from '../ui'
import { formatDay, formatWhen } from '../time'

// ------------------------------------------------------------------ overview dashboard (screen 2)

function IntegrityTile({ label, value, icon, color }: { label: string; value: number; icon: ReactNode; color: string }) {
  return (
    <Paper withBorder p="sm">
      <Group gap="sm" wrap="nowrap">
        <ThemeIcon variant="light" color={color} size={34} radius="xl">
          {icon}
        </ThemeIcon>
        <div>
          <Text fw={700} fz={22} lh={1.1}>
            {value}
          </Text>
          <Text size="xs" c="dimmed">
            {label}
          </Text>
        </div>
      </Group>
    </Paper>
  )
}

export function AdminOverviewPage() {
  const query = useQuery({ queryKey: ['kh', 'admin', 'overview'], queryFn: () => kh.adminOverview() })
  return (
    <Stack gap="md">
      <PageHeader eyebrow="Administration" title="Overview">
        <Text size="sm" c="dimmed">
          Every case of your organisation within your clearance. Nothing here can be deleted.
        </Text>
      </PageHeader>
      <Loaded query={query}>
        {(o) => {
          const activity = o.activity.per_day.map((d) => ({ day: formatDay(d.day).replace(/ \d{4}$/, ''), entries: d.entries }))
          const last30 = o.activity.per_day.reduce((n, d) => n + d.entries, 0)
          const statusRows = WORKFLOW_STATUSES.filter((s) => o.cases.by_status[s]).map((s) => ({ status: workflowLook(s).label, cases: o.cases.by_status[s] }))
          const typeRows = o.cases.by_type.map((t) => ({ type: t.label, cases: t.count }))
          return (
            <Stack gap="md">
              <SimpleGrid cols={{ base: 2, sm: 3, lg: 5 }}>
                <Stat label="Cases" value={o.cases.total} />
                <Stat label="Notes" value={o.files.notes} hint="written in the system" />
                <Stat label="Exhibits" value={o.evidence.items} hint={formatBytes(o.evidence.bytes)} />
                <Stat label="Withdrawn files" value={o.files.withdrawn} hint="kept in the history" />
                <Stat label="History entries" value={o.activity.total} hint={`${last30} in the last 30 days`} />
              </SimpleGrid>

              <ChartPanel title="History entries per day, last 30 days (UTC)" rows={o.activity.per_day.map((d) => [formatDay(d.day), d.entries])}>
                <BarChart
                  h={200}
                  data={activity}
                  dataKey="day"
                  series={CHART_SERIES('entries', 'Entries')}
                  withLegend={false}
                  gridAxis="x"
                  strokeDasharray="0"
                  tickLine="none"
                  maxBarWidth={14}
                  barProps={{ radius: [4, 4, 0, 0] }}
                  xAxisProps={{ interval: 4 }}
                  yAxisProps={{ allowDecimals: false, width: 28 }}
                />
              </ChartPanel>

              <SimpleGrid cols={{ base: 1, md: 2 }}>
                <ChartPanel title="Cases by status" rows={statusRows.map((r) => [r.status, r.cases])}>
                  {statusRows.length ? (
                    <BarChart
                      h={Math.max(120, statusRows.length * 34 + 30)}
                      data={statusRows}
                      dataKey="status"
                      orientation="vertical"
                      series={CHART_SERIES('cases', 'Cases')}
                      withLegend={false}
                      gridAxis="y"
                      strokeDasharray="0"
                      tickLine="none"
                      maxBarWidth={16}
                      barProps={{ radius: [0, 4, 4, 0] }}
                      yAxisProps={{ width: 150 }}
                      xAxisProps={{ allowDecimals: false }}
                    />
                  ) : (
                    <EmptyState title="No cases yet" />
                  )}
                </ChartPanel>
                <ChartPanel title="Cases by type" rows={typeRows.map((r) => [r.type, r.cases])}>
                  {typeRows.length ? (
                    <BarChart
                      h={Math.max(120, typeRows.length * 34 + 30)}
                      data={typeRows}
                      dataKey="type"
                      orientation="vertical"
                      series={CHART_SERIES('cases', 'Cases')}
                      withLegend={false}
                      gridAxis="y"
                      strokeDasharray="0"
                      tickLine="none"
                      maxBarWidth={16}
                      barProps={{ radius: [0, 4, 4, 0] }}
                      yAxisProps={{ width: 150 }}
                      xAxisProps={{ allowDecimals: false }}
                    />
                  ) : (
                    <EmptyState title="No cases yet" />
                  )}
                </ChartPanel>
              </SimpleGrid>

              <Grid gap="md">
                <Grid.Col span={{ base: 12, md: 5 }}>
                  <Panel title="Evidence integrity (latest check of each exhibit)" actions={<Anchor component={Link} to="/kh/admin/evidence" size="xs">Registry</Anchor>}>
                    <SimpleGrid cols={2}>
                      <IntegrityTile label="Intact" value={o.evidence.integrity.match ?? 0} icon={<IconShieldCheck size={18} />} color="green" />
                      <IntegrityTile label="Changed" value={o.evidence.integrity.mismatch ?? 0} icon={<IconShieldX size={18} />} color="red" />
                      <IntegrityTile label="File missing" value={o.evidence.integrity.missing ?? 0} icon={<IconAlertTriangle size={18} />} color="red" />
                      <IntegrityTile label="Not checked yet" value={o.evidence.integrity.never_checked ?? 0} icon={<IconQuestionMark size={18} />} color="yellow" />
                    </SimpleGrid>
                    {o.evidence.alerts.length > 0 && (
                      <Alert color="red" mt="sm" p="xs" icon={<IconShieldX size={16} />} title="Needs attention">
                        <Stack gap={4}>
                          {o.evidence.alerts.map((a) => (
                            <Text key={a.evidence_id} size="xs">
                              <Anchor component={Link} to={`/kh/evidence/${a.evidence_id}`} size="xs" ff="monospace">
                                {a.display_id}
                              </Anchor>{' '}
                              ({a.case_display_id}) {a.title}: {a.result} on {formatWhen(a.checked_at)}
                            </Text>
                          ))}
                        </Stack>
                      </Alert>
                    )}
                  </Panel>
                </Grid.Col>
                <Grid.Col span={{ base: 12, md: 7 }}>
                  <Panel title="Recent activity" actions={<Anchor component={Link} to="/kh/admin/activity" size="xs">More</Anchor>}>
                    <Stack gap={6}>
                      {o.recent_entries.slice(0, 8).map((e) => (
                        <Group key={`${e.case.id}-${e.seq}`} justify="space-between" wrap="nowrap">
                          <Group gap="xs" wrap="nowrap" style={{ minWidth: 0 }}>
                            <EntryBadge value={e.kind} />
                            <Text size="sm" truncate>
                              {e.summary}
                            </Text>
                          </Group>
                          <Group gap="xs" wrap="nowrap">
                            <Text size="xs" c="dimmed" ff="monospace" style={{ whiteSpace: 'nowrap' }}>
                              {e.case.display_id}
                            </Text>
                            <When at={e.at} size="xs" />
                          </Group>
                        </Group>
                      ))}
                      {o.recent_entries.length === 0 && (
                        <Text size="sm" c="dimmed">
                          No activity yet.
                        </Text>
                      )}
                    </Stack>
                  </Panel>
                </Grid.Col>
              </Grid>
            </Stack>
          )
        }}
      </Loaded>
    </Stack>
  )
}

// ------------------------------------------------------------------ case registry (screen 4)

export function AdminCasesPage() {
  const navigate = useNavigate()
  const [q, setQ] = useState('')
  const [status, setStatus] = useState<string | null>(null)
  const [debounced] = useDebouncedValue(q, 300)
  const query = useInfiniteQuery({
    queryKey: ['kh', 'admin', 'registry', debounced, status],
    queryFn: ({ pageParam }) => kh.registry({ q: debounced || undefined, workflow_status: status, limit: 50, cursor: pageParam }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
  })
  const items = query.data?.pages.flatMap((p) => p.items) ?? []
  return (
    <Stack gap="md">
      <PageHeader eyebrow="Administration" title="All cases">
        <Text size="sm" c="dimmed">
          {query.data?.pages[0]?.total ?? '…'} cases. Select one to see its history, its team's access and its audit trail.
        </Text>
      </PageHeader>
      <Group gap="sm">
        <TextInput leftSection={<IconSearch size={14} />} placeholder="Case ID or title" value={q} onChange={(e) => setQ(e.currentTarget.value)} w={300} size="xs" />
        <Select size="xs" w={220} placeholder="Any status" data={WORKFLOW_STATUSES.map((s) => ({ value: s, label: workflowLook(s).label }))} value={status} onChange={setStatus} clearable />
      </Group>
      <Paper withBorder radius="sm" style={{ overflowX: 'auto' }}>
        {items.length === 0 && !query.isPending ? (
          <EmptyState title="No cases found" />
        ) : (
          <Table miw={1200}>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Case ID</Table.Th>
                <Table.Th>Title</Table.Th>
                <Table.Th>Official reference</Table.Th>
                <Table.Th>Type</Table.Th>
                <Table.Th>Station</Table.Th>
                <Table.Th>Investigator</Table.Th>
                <Table.Th>Last activity</Table.Th>
                <Table.Th>Status</Table.Th>
                <Table.Th ta="right">Entries</Table.Th>
                <Table.Th ta="right">Files</Table.Th>
                <Table.Th ta="right">Exhibits</Table.Th>
                <Table.Th>Priority</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {items.map((c) => (
                <Table.Tr key={c.id} onClick={() => navigate(`/kh/admin/cases/${c.id}`)} style={{ cursor: 'pointer' }}>
                  <Table.Td>
                    <Anchor component={Link} to={`/kh/admin/cases/${c.id}`} ff="monospace" size="sm" fw={600} onClick={(e) => e.stopPropagation()}>
                      {c.display_id}
                    </Anchor>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" lineClamp={2}>
                      {c.title}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="xs">{c.official_references.join(', ') || '—'}</Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="xs">{c.case_type_label}</Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="xs" ff="monospace">
                      {c.station_code}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    {c.leads.length ? c.leads.map((p) => <PersonName key={p.id} person={p} size="xs" />) : <Text size="xs" c="dimmed">—</Text>}
                  </Table.Td>
                  <Table.Td>
                    <When at={c.last_activity} size="xs" />
                  </Table.Td>
                  <Table.Td>
                    <WorkflowBadge value={c.workflow_status} />
                  </Table.Td>
                  <Table.Td ta="right">
                    <Text size="sm">{c.entries}</Text>
                  </Table.Td>
                  <Table.Td ta="right">
                    <Text size="sm">{c.files}</Text>
                  </Table.Td>
                  <Table.Td ta="right">
                    <Text size="sm">{c.evidence_count}</Text>
                  </Table.Td>
                  <Table.Td>
                    <PriorityBadge value={c.priority} />
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        )}
      </Paper>
      {query.hasNextPage && (
        <Button variant="default" size="xs" onClick={() => query.fetchNextPage()} loading={query.isFetchingNextPage}>
          More
        </Button>
      )}
    </Stack>
  )
}

// ------------------------------------------------------------------ one case: its history, access and audit trail (screen 14)

export function AdminCasePage() {
  const { caseId = '' } = useParams()
  const detail = useQuery({ queryKey: ['kh', 'case', caseId], queryFn: () => kh.case(caseId) })
  const history = useQuery({ queryKey: ['kh', 'admin', 'history', caseId], queryFn: () => kh.history(caseId, { limit: 500 }) })
  const access = useQuery({ queryKey: ['kh', 'admin', 'access', caseId], queryFn: () => kh.adminAccessHistory(caseId) })
  return (
    <Loaded query={detail}>
      {(c) => (
        <Stack gap="md">
          <PageHeader
            eyebrow={<Anchor component={Link} to="/kh/admin/cases" size="xs">← All cases</Anchor>}
            title={
              <>
                <Text span ff="monospace" inherit c="hawk.3">
                  {c.display_id}
                </Text>{' '}
                {c.title}
              </>
            }
            actions={
              <Button variant="default" component={Link} to={`/kh/case/${c.id}`}>
                Open the case
              </Button>
            }
          >
            <Group gap="xs">
              <WorkflowBadge value={c.workflow_status} />
              <PriorityBadge value={c.priority} />
              <Text size="sm" c="dimmed">
                {c.folders.length} folders · {c.folders.reduce((n, f) => n + f.files, 0)} files · {c.team.filter((m) => !m.revoked_at).length} on the team
              </Text>
            </Group>
          </PageHeader>
          <Tabs defaultValue="history" keepMounted={false}>
            <Tabs.List>
              <Tabs.Tab value="history">History</Tabs.Tab>
              <Tabs.Tab value="access">Access history</Tabs.Tab>
              <Tabs.Tab value="audit">Audit trail</Tabs.Tab>
            </Tabs.List>
            <Tabs.Panel value="history" pt="md">
              <Loaded query={history}>
                {(view) =>
                  view.entries.length === 0 ? (
                    <EmptyState title="No entries" />
                  ) : (
                    <Paper withBorder radius="sm">
                      <Table>
                        <Table.Tbody>
                          {view.entries.map((e) => (
                            <Table.Tr key={e.seq}>
                              <Table.Td w={60}>
                                <Text size="sm" fw={600}>
                                  {e.seq}
                                </Text>
                              </Table.Td>
                              <Table.Td>
                                <Group gap="xs" wrap="nowrap">
                                  <EntryBadge value={e.kind} />
                                  <Text size="sm">{e.summary}</Text>
                                </Group>
                              </Table.Td>
                              <Table.Td>
                                <PersonName person={e.actor} size="xs" />
                              </Table.Td>
                              <Table.Td>
                                <When at={e.at} size="xs" />
                              </Table.Td>
                            </Table.Tr>
                          ))}
                        </Table.Tbody>
                      </Table>
                    </Paper>
                  )
                }
              </Loaded>
            </Tabs.Panel>
            <Tabs.Panel value="access" pt="md">
              <Loaded query={access}>
                {(events) =>
                  events.length === 0 ? (
                    <EmptyState title="No access changes" />
                  ) : (
                    <Paper withBorder p="md">
                      <Timeline bulletSize={14} lineWidth={2}>
                        {events.map((e) => (
                          <Timeline.Item key={e.id} color={e.change === 'membership_granted' ? 'green' : 'orange'}>
                            <Text size="sm">
                              <b>{e.user?.display_name}</b> {e.change === 'membership_granted' ? `became ${roleLabel(e.new_value)}` : `stopped being ${roleLabel(e.old_value)}`}
                            </Text>
                            <Text size="xs" c="dimmed">
                              {formatWhen(e.at)} · by {e.actor?.display_name ?? '—'}
                              {e.reason ? ` · “${e.reason}”` : ''}
                            </Text>
                          </Timeline.Item>
                        ))}
                      </Timeline>
                    </Paper>
                  )
                }
              </Loaded>
            </Tabs.Panel>
            <Tabs.Panel value="audit" pt="md">
              <CaseAuditTrail caseId={c.id} />
            </Tabs.Panel>
          </Tabs>
        </Stack>
      )}
    </Loaded>
  )
}

// ------------------------------------------------------------------ evidence integrity registry

export function AdminEvidencePage() {
  const query = useInfiniteQuery({
    queryKey: ['kh', 'admin', 'integrity'],
    queryFn: ({ pageParam }) => kh.integrityReport({ limit: 100, cursor: pageParam }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
  })
  const first = query.data?.pages[0]
  const items = query.data?.pages.flatMap((p) => p.items) ?? []
  return (
    <Stack gap="md">
      <PageHeader eyebrow="Administration" title="Evidence integrity">
        <Text size="sm" c="dimmed">
          Every exhibit and the result of its latest check. A scheduled check of everything runs with{' '}
          <Text span ff="monospace" size="sm">
            python -m scripts.verify_evidence
          </Text>
          ; open an exhibit to check it now.
        </Text>
      </PageHeader>
      {first && (
        <SimpleGrid cols={{ base: 2, sm: 4 }}>
          <IntegrityTile label="Intact" value={first.counts.match ?? 0} icon={<IconShieldCheck size={18} />} color="green" />
          <IntegrityTile label="Changed" value={first.counts.mismatch ?? 0} icon={<IconShieldX size={18} />} color="red" />
          <IntegrityTile label="File missing" value={first.counts.missing ?? 0} icon={<IconAlertTriangle size={18} />} color="red" />
          <IntegrityTile label="Not checked yet" value={first.counts.never_checked ?? 0} icon={<IconQuestionMark size={18} />} color="yellow" />
        </SimpleGrid>
      )}
      <Paper withBorder radius="sm">
        <Table>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Exhibit</Table.Th>
              <Table.Th>Case</Table.Th>
              <Table.Th>Size</Table.Th>
              <Table.Th>Latest check</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {items.map((i) => (
              <Table.Tr key={i.evidence.id}>
                <Table.Td>
                  <Anchor component={Link} to={`/kh/evidence/${i.evidence.id}`} size="sm" ff="monospace" fw={600}>
                    {i.evidence.display_id}
                  </Anchor>{' '}
                  <Text span size="sm">
                    {i.evidence.title}
                  </Text>
                  {i.sealed && (
                    <Badge size="xs" color="orange" ml={6}>
                      sealed
                    </Badge>
                  )}
                </Table.Td>
                <Table.Td>
                  <Text size="xs" ff="monospace">
                    {i.case.display_id}
                  </Text>
                </Table.Td>
                <Table.Td>
                  <Text size="xs">{formatBytes(i.size_bytes)}</Text>
                </Table.Td>
                <Table.Td>
                  <Group gap={6} wrap="nowrap">
                    <IntegrityBadge result={i.last_check?.result ?? null} />
                    {i.last_check && <When at={i.last_check.checked_at} size="xs" />}
                  </Group>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
        {items.length === 0 && !query.isPending && <EmptyState title="No evidence yet" />}
      </Paper>
      {query.hasNextPage && (
        <Button variant="default" size="xs" onClick={() => query.fetchNextPage()} loading={query.isFetchingNextPage}>
          More
        </Button>
      )}
    </Stack>
  )
}

// ------------------------------------------------------------------ investigation activity

export function AdminActivityPage() {
  const query = useQuery({ queryKey: ['kh', 'admin', 'overview'], queryFn: () => kh.adminOverview() })
  return (
    <Stack gap="md">
      <PageHeader eyebrow="Administration" title="Investigation activity">
        <Text size="sm" c="dimmed">
          The latest entries of the cases' histories across the organisation. Each case's whole history is on its case page.
        </Text>
      </PageHeader>
      <Loaded query={query}>
        {(o) => (
          <Paper withBorder radius="sm">
            <Table>
              <Table.Tbody>
                {o.recent_entries.map((e) => (
                  <Table.Tr key={`${e.case.id}-${e.seq}`}>
                    <Table.Td>
                      <Group gap="xs" wrap="nowrap">
                        <EntryBadge value={e.kind} />
                        <Text size="sm">{e.summary}</Text>
                      </Group>
                    </Table.Td>
                    <Table.Td>
                      <Anchor component={Link} to={`/kh/admin/cases/${e.case.id}`} size="xs" ff="monospace">
                        {e.case.display_id}
                      </Anchor>
                      <Text span size="xs" c="dimmed">
                        {' '}
                        · entry {e.seq}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <PersonName person={e.actor} size="xs" />
                    </Table.Td>
                    <Table.Td>
                      <When at={e.at} size="xs" />
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
            {o.recent_entries.length === 0 && <EmptyState title="No activity yet" />}
          </Paper>
        )}
      </Loaded>
    </Stack>
  )
}
