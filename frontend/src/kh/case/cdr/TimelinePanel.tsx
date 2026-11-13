// Feature 7: Communication timeline for a specific number.

import { Badge, Box, Button, Group, Paper, Stack, Table, Text, TextInput, Title } from '@mantine/core'
import { IconSearch } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { kh } from '../../api'
import type { CdrRecord } from '../../types'
import { EmptyState, Loaded } from '../../ui'

interface Props {
  caseId: string
}

function dirBadge(dir: CdrRecord['call_direction']) {
  if (!dir) return null
  return (
    <Badge size="xs" variant="light" color={dir === 'incoming' ? 'blue' : 'green'}>
      {dir === 'incoming' ? '← in' : 'out →'}
    </Badge>
  )
}

function svcBadge(svc: CdrRecord['service_type']) {
  if (!svc) return null
  const col = svc === 'voice' ? 'teal' : svc === 'sms' ? 'orange' : 'grape'
  return <Badge size="xs" variant="outline" color={col}>{svc}</Badge>
}

export function CdrTimelinePanel({ caseId }: Props) {
  const [number, setNumber] = useState('')
  const [submitted, setSubmitted] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  const query = useQuery({
    queryKey: ['kh', 'cdr', caseId, 'timeline', submitted, dateFrom, dateTo],
    queryFn: () =>
      kh.cdrTimeline(caseId, submitted, {
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        limit: 300,
      }),
    enabled: submitted.length >= 3,
  })

  const submit = () => { if (number.trim().length >= 3) setSubmitted(number.trim()) }

  return (
    <Stack gap="md">
      <Stack gap={4}>
        <Title order={5} fw={600}>Communication Timeline</Title>
        <Text size="sm" c="dimmed">
          All events for a single subscriber in chronological order.
        </Text>
      </Stack>

      <Group gap="xs" wrap="wrap" align="flex-end">
        <TextInput
          label="Phone number"
          placeholder="MSISDN to view"
          value={number}
          onChange={(e) => setNumber(e.currentTarget.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') submit() }}
          leftSection={<IconSearch size={14} />}
          style={{ flex: 1, minWidth: 200 }}
          size="sm"
        />
        <TextInput
          label="From date"
          placeholder="YYYY-MM-DD"
          value={dateFrom}
          onChange={(e) => setDateFrom(e.currentTarget.value)}
          size="sm"
          style={{ width: 140 }}
        />
        <TextInput
          label="To date"
          placeholder="YYYY-MM-DD"
          value={dateTo}
          onChange={(e) => setDateTo(e.currentTarget.value)}
          size="sm"
          style={{ width: 140 }}
        />
        <Button size="sm" mt={24} onClick={submit} disabled={number.trim().length < 3}>
          Show Timeline
        </Button>
      </Group>

      {!submitted && (
        <EmptyState title="Enter a number above">
          Type or paste a phone number to see its full call timeline.
        </EmptyState>
      )}

      {submitted && (
        <Loaded query={query}>
          {(data) =>
            data.total === 0 ? (
              <EmptyState title="No events found">
                No CDR records match {submitted} in this case.
              </EmptyState>
            ) : (
              <Paper withBorder radius="sm">
                <Group px="sm" py="xs" gap="xs">
                  <Text size="sm" fw={600} ff="monospace">{submitted}</Text>
                  <Badge>{data.total} events</Badge>
                </Group>
                <Box style={{ overflowX: 'auto' }}>
                  <Table striped highlightOnHover withColumnBorders>
                    <Table.Thead>
                      <Table.Tr>
                        <Table.Th>Time (UTC)</Table.Th>
                        <Table.Th>Direction</Table.Th>
                        <Table.Th>Service</Table.Th>
                        <Table.Th>Other Party</Table.Th>
                        <Table.Th>Duration</Table.Th>
                        <Table.Th>Cell ID</Table.Th>
                      </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                      {data.items.map((r) => {
                        const isA = r.a_party_canonical === submitted || r.a_party === submitted
                        const other = isA
                          ? (r.b_party_canonical ?? r.b_party)
                          : (r.a_party_canonical ?? r.a_party)
                        const dur = r.duration_seconds != null
                          ? r.duration_seconds < 60
                            ? `${r.duration_seconds}s`
                            : `${Math.floor(r.duration_seconds / 60)}m ${r.duration_seconds % 60}s`
                          : '—'
                        return (
                          <Table.Tr key={r.id}>
                            <Table.Td>
                              <Text size="xs" ff="monospace">
                                {r.timestamp_utc
                                  ? new Date(r.timestamp_utc).toLocaleString()
                                  : '—'}
                              </Text>
                            </Table.Td>
                            <Table.Td>{dirBadge(r.call_direction)}</Table.Td>
                            <Table.Td>{svcBadge(r.service_type)}</Table.Td>
                            <Table.Td>
                              <Text size="xs" ff="monospace">{other ?? '—'}</Text>
                            </Table.Td>
                            <Table.Td><Text size="xs">{dur}</Text></Table.Td>
                            <Table.Td>
                              <Text size="xs" ff="monospace">{r.cell_id ?? '—'}</Text>
                            </Table.Td>
                          </Table.Tr>
                        )
                      })}
                    </Table.Tbody>
                  </Table>
                </Box>
              </Paper>
            )
          }
        </Loaded>
      )}
    </Stack>
  )
}
