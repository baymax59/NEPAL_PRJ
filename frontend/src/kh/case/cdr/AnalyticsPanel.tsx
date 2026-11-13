// CDR analytics: frequency charts, top contacts, summary stats.

import { BarChart } from '@mantine/charts'
import { Badge, Grid, Paper, SimpleGrid, Stack, Table, Text, Title } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { kh } from '../../api'
import { EmptyState, Loaded } from '../../ui'

interface Props {
  caseId: string
}

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <Paper withBorder p="sm" radius="sm">
      <Text size="xs" c="dimmed" tt="uppercase" fw={600} style={{ letterSpacing: 0.5 }}>{label}</Text>
      <Text size="lg" fw={700} mt={2}>{value}</Text>
    </Paper>
  )
}

export function CdrAnalyticsPanel({ caseId }: Props) {
  const summary = useQuery({ queryKey: ['kh', 'case', caseId, 'cdr', 'summary'], queryFn: () => kh.cdrSummary(caseId) })
  const topContacts = useQuery({ queryKey: ['kh', 'case', caseId, 'cdr', 'top-contacts'], queryFn: () => kh.cdrTopContacts(caseId) })
  const hourFreq = useQuery({ queryKey: ['kh', 'case', caseId, 'cdr', 'freq-hour'], queryFn: () => kh.cdrFrequencyByHour(caseId) })

  const hours = Array.from({ length: 24 }, (_, i) => i)
  const freqData = hours.map((h) => ({
    hour: `${String(h).padStart(2, '0')}:00`,
    calls: hourFreq.data?.find((r) => r.hour === h)?.count ?? 0,
  }))

  return (
    <Stack gap="md">
      {/* Summary stats */}
      <Loaded query={summary}>
        {(s) =>
          s.total_records === 0 ? (
            <EmptyState title="No records to analyse">Import a CDR file first.</EmptyState>
          ) : (
            <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="sm">
              <StatCard label="Total records" value={s.total_records.toLocaleString()} />
              <StatCard label="Unique subscribers" value={s.unique_subscribers.toLocaleString()} />
              <StatCard label="Earliest" value={s.earliest ? new Date(s.earliest).toLocaleDateString() : '—'} />
              <StatCard label="Latest" value={s.latest ? new Date(s.latest).toLocaleDateString() : '—'} />
            </SimpleGrid>
          )
        }
      </Loaded>

      <Grid gap="md">
        {/* Calls by hour */}
        <Grid.Col span={{ base: 12, md: 7 }}>
          <Paper withBorder p="md" radius="sm">
            <Title order={5} fw={600} mb="sm">Calls by hour of day (UTC)</Title>
            <Loaded query={hourFreq}>
              {() => (
                <BarChart
                  h={200}
                  data={freqData}
                  dataKey="hour"
                  series={[{ name: 'calls', color: 'hawk.4', label: 'Calls' }]}
                  withLegend={false}
                  withTooltip
                  yAxisProps={{ width: 40 }}
                  xAxisProps={{ tick: { fontSize: 10 }, interval: 3 }}
                />
              )}
            </Loaded>
          </Paper>
        </Grid.Col>

        {/* Top contacts */}
        <Grid.Col span={{ base: 12, md: 5 }}>
          <Paper withBorder p="md" radius="sm" style={{ height: '100%' }}>
            <Title order={5} fw={600} mb="sm">Top contacts</Title>
            <Loaded query={topContacts}>
              {(contacts) =>
                contacts.length === 0 ? (
                  <Text size="sm" c="dimmed">No data yet</Text>
                ) : (
                  <Table>
                    <Table.Thead>
                      <Table.Tr>
                        <Table.Th>Number</Table.Th>
                        <Table.Th ta="right">Calls</Table.Th>
                      </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                      {contacts.slice(0, 15).map((c) => (
                        <Table.Tr key={c.number}>
                          <Table.Td>
                            <Text size="xs" ff="monospace">{c.number}</Text>
                          </Table.Td>
                          <Table.Td ta="right">
                            <Badge size="sm" variant="light" color="hawk">{c.count}</Badge>
                          </Table.Td>
                        </Table.Tr>
                      ))}
                    </Table.Tbody>
                  </Table>
                )
              }
            </Loaded>
          </Paper>
        </Grid.Col>
      </Grid>
    </Stack>
  )
}
