// CDR records table with search and filter.

import { Badge, Box, Button, Group, Pagination, Paper, Select, Stack, Table, Text, TextInput } from '@mantine/core'
import { IconSearch, IconX } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { kh } from '../../api'
import type { CdrRecord } from '../../types'
import { EmptyState, Loaded } from '../../ui'

const PAGE_SIZE = 100

interface Props {
  caseId: string
}

function directionBadge(dir: CdrRecord['call_direction']) {
  if (!dir) return null
  return <Badge size="xs" color={dir === 'incoming' ? 'blue' : 'green'} variant="light">{dir}</Badge>
}

function serviceBadge(svc: CdrRecord['service_type']) {
  if (!svc) return null
  return <Badge size="xs" color={svc === 'voice' ? 'teal' : svc === 'sms' ? 'orange' : 'grape'} variant="outline">{svc}</Badge>
}

function formatTs(ts: string | null) {
  if (!ts) return <Text span c="dimmed" size="xs">—</Text>
  return new Date(ts).toLocaleString()
}

function formatDuration(s: number | null) {
  if (s == null) return <Text span c="dimmed" size="xs">—</Text>
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  const rem = s % 60
  return `${m}m ${rem}s`
}

export function CdrRecordsTable({ caseId }: Props) {
  const [q, setQ] = useState('')
  const [party, setParty] = useState('')
  const [direction, setDirection] = useState<string | null>(null)
  const [service, setService] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [includeDuplicates, setIncludeDuplicates] = useState(false)

  const params = {
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
    ...(q ? { q } : {}),
    ...(party ? { party } : {}),
    ...(direction ? { direction } : {}),
    ...(service ? { service_type: service } : {}),
    include_duplicates: includeDuplicates,
  }

  const query = useQuery({
    queryKey: ['kh', 'case', caseId, 'cdr', 'records', params],
    queryFn: () => kh.cdrRecords(caseId, params),
  })

  const total = query.data?.total ?? 0
  const items = query.data?.items ?? []
  const totalPages = Math.ceil(total / PAGE_SIZE)

  const hasFilter = !!(q || party || direction || service)
  const clearFilters = () => { setQ(''); setParty(''); setDirection(null); setService(null); setPage(1) }

  return (
    <Stack gap="sm">
      <Group gap="xs" wrap="wrap">
        <TextInput
          placeholder="Search numbers, IMEI, cell ID…"
          value={q}
          onChange={(e) => { setQ(e.currentTarget.value); setPage(1) }}
          leftSection={<IconSearch size={14} />}
          size="xs"
          style={{ flex: 1, minWidth: 200 }}
        />
        <TextInput
          placeholder="Specific number"
          value={party}
          onChange={(e) => { setParty(e.currentTarget.value); setPage(1) }}
          size="xs"
          style={{ width: 180 }}
        />
        <Select
          placeholder="Direction"
          value={direction}
          onChange={(v) => { setDirection(v); setPage(1) }}
          data={[
            { value: 'incoming', label: 'Incoming' },
            { value: 'outgoing', label: 'Outgoing' },
          ]}
          clearable
          size="xs"
          style={{ width: 130 }}
        />
        <Select
          placeholder="Service"
          value={service}
          onChange={(v) => { setService(v); setPage(1) }}
          data={[
            { value: 'voice', label: 'Voice' },
            { value: 'sms', label: 'SMS' },
            { value: 'data', label: 'Data' },
          ]}
          clearable
          size="xs"
          style={{ width: 110 }}
        />
        {hasFilter && (
          <Button size="xs" variant="subtle" color="gray" leftSection={<IconX size={12} />} onClick={clearFilters}>
            Clear
          </Button>
        )}
        <Button
          size="xs"
          variant={includeDuplicates ? 'filled' : 'default'}
          onClick={() => { setIncludeDuplicates(!includeDuplicates); setPage(1) }}
        >
          {includeDuplicates ? 'Hiding dupes' : 'Show dupes'}
        </Button>
      </Group>

      <Loaded query={query}>
        {() =>
          items.length === 0 ? (
            <EmptyState title={hasFilter ? 'No records match your filter' : 'No CDR records yet'} />
          ) : (
            <Paper withBorder radius="sm">
              <Box style={{ overflowX: 'auto' }}>
                <Table striped highlightOnHover withColumnBorders>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>A-Party</Table.Th>
                      <Table.Th>B-Party</Table.Th>
                      <Table.Th>Timestamp (UTC)</Table.Th>
                      <Table.Th>Duration</Table.Th>
                      <Table.Th>Direction</Table.Th>
                      <Table.Th>Service</Table.Th>
                      <Table.Th>Gen</Table.Th>
                      <Table.Th>Cell ID</Table.Th>
                      <Table.Th>IMEI</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {items.map((r) => (
                      <Table.Tr key={r.id} opacity={r.is_duplicate ? 0.5 : 1}>
                        <Table.Td>
                          <Text size="xs" ff="monospace">{r.a_party_canonical ?? r.a_party ?? '—'}</Text>
                        </Table.Td>
                        <Table.Td>
                          <Text size="xs" ff="monospace">{r.b_party_canonical ?? r.b_party ?? '—'}</Text>
                        </Table.Td>
                        <Table.Td>
                          <Text size="xs">{formatTs(r.timestamp_utc)}</Text>
                        </Table.Td>
                        <Table.Td>
                          <Text size="xs">{formatDuration(r.duration_seconds)}</Text>
                        </Table.Td>
                        <Table.Td>{directionBadge(r.call_direction)}</Table.Td>
                        <Table.Td>{serviceBadge(r.service_type)}</Table.Td>
                        <Table.Td>
                          <Text size="xs">{r.network_generation ?? '—'}</Text>
                        </Table.Td>
                        <Table.Td>
                          <Text size="xs" ff="monospace">{r.cell_id ?? '—'}</Text>
                        </Table.Td>
                        <Table.Td>
                          <Text size="xs" ff="monospace">{r.imei ?? '—'}</Text>
                        </Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </Box>
              <Group justify="space-between" px="sm" py="xs" wrap="wrap" gap="xs">
                <Text size="xs" c="dimmed">{total.toLocaleString()} record{total !== 1 ? 's' : ''}</Text>
                {totalPages > 1 && (
                  <Pagination value={page} onChange={setPage} total={totalPages} size="xs" />
                )}
              </Group>
            </Paper>
          )
        }
      </Loaded>
    </Stack>
  )
}
