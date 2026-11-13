// Station and officer dashboards (phase R-5, docs/case-management/12-roles-and-stations.md §7): open, closed and pending cases of each
// police station, and how each officer is getting on. Read only. What is shown depends on the role (a Super Admin every station, an
// Administrator or Supervisor their own station(s), an Investigator only themselves); the backend counts only cases the viewer may open
// and answers "not found" for stations and officers outside their reach.

import { Alert, Anchor, Badge, Group, SimpleGrid, Stack, Table, Text } from '@mantine/core'
import { BarChart } from '@mantine/charts'
import { IconArrowLeft } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { Link, Navigate, useParams } from 'react-router'
import { useAuth } from '../../auth/useAuth'
import { kh } from '../api'
import { CHART_SERIES, ChartPanel } from '../charts'
import { roleLabel, WORKFLOW_STATUSES, workflowLook } from '../labels'
import type { CaseFigures, OfficerDashboard, StationDashboard } from '../types'
import { EmptyState, Loaded, PageHeader, Panel, PriorityBadge, Stat, When, WorkflowBadge } from '../ui'

const days = (n: number | null | undefined) => (n == null ? '—' : n === 1 ? '1 day' : `${n} days`)
const monthLabel = (month: string) => new Intl.DateTimeFormat('en-IN', { month: 'short', year: 'numeric', timeZone: 'UTC' }).format(new Date(`${month}-01T00:00:00Z`))
const WORDS = 'Figures count only the cases you may open. Open means not closed or archived (it includes the two pending groups); closed means closed or archived.'

function FigureTiles({ f }: { f: CaseFigures }) {
  return (
    <SimpleGrid cols={{ base: 2, sm: 3, lg: 6 }}>
      <Stat label="Open cases" value={f.open} hint={`${f.total} in all`} />
      <Stat label="Pending evidence" value={f.pending_evidence} />
      <Stat label="Pending review" value={f.pending_review} />
      <Stat label="Closed" value={f.closed} />
      <Stat label="New this month" value={f.new_this_month} />
      <Stat label="Average to close" value={days(f.average_days_to_close)} hint="cases now closed" />
    </SimpleGrid>
  )
}

function Back({ to, children }: { to: string; children: string }) {
  return (
    <Anchor component={Link} to={to} size="sm">
      <Group gap={4} display="inline-flex">
        <IconArrowLeft size={14} />
        {children}
      </Group>
    </Anchor>
  )
}

// ------------------------------------------------------------------ the way in

/** An Investigator goes straight to their own page, someone with one station straight to it; the rest choose a station. */
export function PerformancePage() {
  const { user } = useAuth()
  const isInvestigator = user?.org_role === 'investigator'
  const stations = useQuery({ queryKey: ['kh', 'dashboard', 'stations'], queryFn: () => kh.dashboardStations(), enabled: !isInvestigator })
  if (isInvestigator && user) return <Navigate to={`/kh/performance/officers/${user.id}`} replace />
  return (
    <Stack gap="md">
      <PageHeader eyebrow="Station dashboards" title="Police stations">
        <Text size="sm" c="dimmed">
          {WORDS}
        </Text>
      </PageHeader>
      <Loaded query={stations}>
        {(data) => {
          if (data.stations.length === 1 && user?.org_role !== 'super_admin') {
            return <Navigate to={`/kh/performance/stations/${data.stations[0].station.id}`} replace />
          }
          if (data.stations.length === 0) {
            return (
              <EmptyState title="No police station">
                You are not assigned to a police station yet. A person above you can assign one under People &amp; stations.
              </EmptyState>
            )
          }
          const sum = (pick: (f: CaseFigures) => number) => data.stations.reduce((n, row) => n + pick(row.figures), 0)
          return (
            <Stack gap="md">
              <SimpleGrid cols={{ base: 2, sm: 4 }}>
                <Stat label="Stations" value={data.stations.length} />
                <Stat label="Open cases" value={sum((f) => f.open)} hint={`${sum((f) => f.total)} in all`} />
                <Stat label="Pending case" value={sum((f) => f.pending_evidence + f.pending_review)} />
                <Stat label="Closed" value={sum((f) => f.closed)} />
              </SimpleGrid>
              <Panel p="0">
                <Table highlightOnHover>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Station</Table.Th>
                      <Table.Th ta="right">Open</Table.Th>
                      <Table.Th ta="right">Pending evidence</Table.Th>
                      <Table.Th ta="right">Pending review</Table.Th>
                      <Table.Th ta="right">Closed</Table.Th>
                      <Table.Th ta="right">New this month</Table.Th>
                      <Table.Th ta="right">Average to close</Table.Th>
                      <Table.Th>Open the longest</Table.Th>
                      <Table.Th ta="right">People</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {data.stations.map(({ station, figures, officers }) => {
                      const oldest = figures.oldest_open[0]
                      return (
                        <Table.Tr key={station.id}>
                          <Table.Td>
                            <Anchor component={Link} to={`/kh/performance/stations/${station.id}`} size="sm" fw={600}>
                              {station.code}
                            </Anchor>
                            <Text size="xs" c="dimmed">
                              {station.name}
                              {station.status !== 'active' && ' (inactive)'}
                            </Text>
                          </Table.Td>
                          <Table.Td ta="right">{figures.open}</Table.Td>
                          <Table.Td ta="right">{figures.pending_evidence}</Table.Td>
                          <Table.Td ta="right">{figures.pending_review}</Table.Td>
                          <Table.Td ta="right">{figures.closed}</Table.Td>
                          <Table.Td ta="right">{figures.new_this_month}</Table.Td>
                          <Table.Td ta="right">{days(figures.average_days_to_close)}</Table.Td>
                          <Table.Td>
                            {oldest ? (
                              <>
                                <Anchor component={Link} to={`/kh/case/${oldest.case.id}`} size="sm" ff="monospace">
                                  {oldest.case.display_id}
                                </Anchor>{' '}
                                <Text span size="xs" c="dimmed">
                                  {days(oldest.days_open)}
                                </Text>
                              </>
                            ) : (
                              <Text size="sm" c="dimmed">
                                —
                              </Text>
                            )}
                          </Table.Td>
                          <Table.Td ta="right">{officers}</Table.Td>
                        </Table.Tr>
                      )
                    })}
                  </Table.Tbody>
                </Table>
              </Panel>
            </Stack>
          )
        }}
      </Loaded>
    </Stack>
  )
}

// ------------------------------------------------------------------ one station

function StationBody({ d }: { d: StationDashboard }) {
  const statusRows = WORKFLOW_STATUSES.filter((s) => d.figures.by_status[s]).map((s) => ({ status: workflowLook(s).label, cases: d.figures.by_status[s] }))
  const monthRows = d.monthly.map((m) => ({ month: monthLabel(m.month), opened: m.opened, closed: m.closed }))
  return (
    <Stack gap="md">
      <FigureTiles f={d.figures} />
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
        <ChartPanel title="Opened and closed, month by month" heads={['Month', 'Opened', 'Closed']} rows={monthRows.map((r) => [r.month, r.opened, r.closed])}>
          <BarChart
            h={200}
            data={monthRows}
            dataKey="month"
            series={[
              { name: 'opened', label: 'Opened', color: 'var(--kh-chart-1)' },
              { name: 'closed', label: 'Closed', color: 'var(--kh-chart-2)' },
            ]}
            withLegend
            gridAxis="x"
            strokeDasharray="0"
            tickLine="none"
            maxBarWidth={16}
            barProps={{ radius: [4, 4, 0, 0] }}
            yAxisProps={{ allowDecimals: false, width: 28 }}
          />
        </ChartPanel>
      </SimpleGrid>

      <Panel title="Open the longest" p="0">
        {d.figures.oldest_open.length === 0 ? (
          <EmptyState title="No open cases" />
        ) : (
          <Table>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Case</Table.Th>
                <Table.Th>Status</Table.Th>
                <Table.Th>Priority</Table.Th>
                <Table.Th ta="right">Open for</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {d.figures.oldest_open.map((o) => (
                <Table.Tr key={o.case.id}>
                  <Table.Td>
                    <Anchor component={Link} to={`/kh/case/${o.case.id}`} size="sm" fw={500}>
                      {o.case.title}
                    </Anchor>
                    <Text size="xs" c="dimmed" ff="monospace">
                      {o.case.display_id}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <WorkflowBadge value={o.case.workflow_status} />
                  </Table.Td>
                  <Table.Td>
                    <PriorityBadge value={o.case.priority} />
                  </Table.Td>
                  <Table.Td ta="right">{days(o.days_open)}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        )}
      </Panel>

      <Panel title="Officers" p="0">
        {d.officers.length === 0 ? (
          <EmptyState title="Nobody to show">People who work at this station, below your role, appear here.</EmptyState>
        ) : (
          <Table highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Officer</Table.Th>
                <Table.Th ta="right">Cases</Table.Th>
                <Table.Th ta="right">Open</Table.Th>
                <Table.Th ta="right">Pending</Table.Th>
                <Table.Th ta="right">Closed</Table.Th>
                <Table.Th ta="right">Notes written</Table.Th>
                <Table.Th ta="right">Exhibits added</Table.Th>
                <Table.Th>Last activity</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {d.officers.map((o) => (
                <Table.Tr key={o.person.id}>
                  <Table.Td>
                    <Anchor component={Link} to={`/kh/performance/officers/${o.person.id}`} size="sm" fw={500}>
                      {o.person.display_name}
                    </Anchor>
                    <Text size="xs" c="dimmed">
                      {roleLabel(o.person.org_role)}
                      {o.person.officer ? ` · ${o.person.officer.rank}` : ''}
                    </Text>
                  </Table.Td>
                  <Table.Td ta="right">{o.cases.total}</Table.Td>
                  <Table.Td ta="right">{o.cases.open}</Table.Td>
                  <Table.Td ta="right">{o.cases.pending_evidence + o.cases.pending_review}</Table.Td>
                  <Table.Td ta="right">{o.cases.closed}</Table.Td>
                  <Table.Td ta="right">{o.work.notes}</Table.Td>
                  <Table.Td ta="right">{o.work.evidence}</Table.Td>
                  <Table.Td>
                    <When at={o.last_activity} size="xs" />
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        )}
      </Panel>
    </Stack>
  )
}

export function StationPerformancePage() {
  const { stationId = '' } = useParams()
  const query = useQuery({ queryKey: ['kh', 'dashboard', 'station', stationId], queryFn: () => kh.dashboardStation(stationId) })
  return (
    <Stack gap="md">
      <Back to="/kh/performance">All stations</Back>
      <Loaded query={query}>
        {(d) => (
          <>
            <PageHeader eyebrow="Station dashboard" title={`${d.station.code} · ${d.station.name}`}>
              <Text size="sm" c="dimmed">
                {d.station.district ? `${d.station.district}. ` : ''}
                {WORDS}
              </Text>
            </PageHeader>
            <StationBody d={d} />
          </>
        )}
      </Loaded>
    </Stack>
  )
}

// ------------------------------------------------------------------ one officer

function OfficerBody({ d }: { d: OfficerDashboard }) {
  const mine = d.cases
  return (
    <Stack gap="md">
      <SimpleGrid cols={{ base: 2, sm: 3, lg: 5 }}>
        <Stat label="Cases" value={mine.total} hint="led, worked on or supervised" />
        <Stat label="Open" value={mine.open} />
        <Stat label="Pending evidence" value={mine.pending_evidence} />
        <Stat label="Pending review" value={mine.pending_review} />
        <Stat label="Closed" value={mine.closed} />
      </SimpleGrid>
      <SimpleGrid cols={{ base: 2, sm: 3, lg: 3 }}>
        <Stat label="Notes written" value={d.work.notes} hint="in the cases you may see" />
        <Stat label="Exhibits added" value={d.work.evidence} />
        <Stat label="History entries, last 30 days" value={d.work.entries_last_30_days} hint={`${d.work.entries} in all`} />
      </SimpleGrid>

      <Panel title="Cases" p="0">
        {d.case_list.length === 0 ? (
          <EmptyState title="No cases yet">Cases this person leads, works on or supervises, and that you may open, appear here.</EmptyState>
        ) : (
          <Table highlightOnHover>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Case</Table.Th>
                <Table.Th>Station</Table.Th>
                <Table.Th>Part in the case</Table.Th>
                <Table.Th>Status</Table.Th>
                <Table.Th>Priority</Table.Th>
                <Table.Th>Registered</Table.Th>
                <Table.Th ta="right">Open for</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {d.case_list.map((c) => (
                <Table.Tr key={c.case.id}>
                  <Table.Td>
                    <Anchor component={Link} to={`/kh/case/${c.case.id}`} size="sm" fw={500}>
                      {c.case.title}
                    </Anchor>
                    <Text size="xs" c="dimmed" ff="monospace">
                      {c.case.display_id}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm" ff="monospace">
                      {c.station_code}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="sm">{c.roles.map(roleLabel).join(', ')}</Text>
                    {!c.active && (
                      <Badge size="xs" color="gray" variant="light">
                        no longer on it
                      </Badge>
                    )}
                  </Table.Td>
                  <Table.Td>
                    <WorkflowBadge value={c.case.workflow_status} />
                  </Table.Td>
                  <Table.Td>
                    <PriorityBadge value={c.case.priority} />
                  </Table.Td>
                  <Table.Td>
                    <When at={c.opened_at} size="xs" />
                  </Table.Td>
                  <Table.Td ta="right">{c.days_open == null ? 'closed' : days(c.days_open)}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        )}
      </Panel>
    </Stack>
  )
}

export function OfficerPerformancePage() {
  const { userId = '' } = useParams()
  const { user } = useAuth()
  const query = useQuery({ queryKey: ['kh', 'dashboard', 'officer', userId], queryFn: () => kh.dashboardOfficer(userId) })
  const own = user?.id === userId
  return (
    <Stack gap="md">
      {!own && <Back to="/kh/performance">Station dashboards</Back>}
      <Loaded query={query}>
        {(d) => (
          <>
            <PageHeader eyebrow={own ? 'My performance' : 'Officer dashboard'} title={d.person.display_name}>
              <Text size="sm" c="dimmed">
                {[roleLabel(d.person.org_role), d.person.officer?.rank, d.person.officer ? `ID ${d.person.officer.officer_number}` : null, d.person.stations.map((s) => s.code).join(', ')]
                  .filter(Boolean)
                  .join(' · ')}
                {!d.person.is_active && ' · account ended'}
              </Text>
              <Text size="sm" c="dimmed">
                {WORDS} Last activity: {d.last_activity ? <When at={d.last_activity} /> : 'none yet'}.
              </Text>
            </PageHeader>
            {!d.person.is_active && (
              <Alert color="gray" variant="light">
                This account has ended. Their work and the record stay.
              </Alert>
            )}
            <OfficerBody d={d} />
          </>
        )}
      </Loaded>
    </Stack>
  )
}
