import { Badge, Code, Group, Loader, Pagination, Select, Stack, Table, Text, TextInput, Title, Tooltip } from '@mantine/core'
import { useDebouncedValue } from '@mantine/hooks'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { getAuditLog } from '../api/endpoints'
import { ErrorAlert } from '../components/common'
import { formatDateTime } from '../lib/format'

const PAGE_SIZE = 50
const ACTIONS = [
  'auth.login',
  'search',
  'case.list',
  'case.view',
  'case.explain',
  'case.similar',
  'upload.create',
  'upload.view',
  'upload.similar',
  'upload.delete',
  'role.denied',
  'audit.read',
  'grant.create',
  'grant.revoke',
]
const OUTCOMES = ['success', 'denied', 'not_found', 'rejected', 'error']

function shorten(value: string, max: number): string {
  return value.length > max ? `${value.slice(0, max - 1)}…` : value
}

/** Event details as short "key: value" lines; long values (IDs, fingerprints) are shortened, full on hover. */
function Details({ details }: { details: Record<string, unknown> }) {
  return Object.entries(details).map(([key, value]) => {
    const text = typeof value === 'string' ? value : JSON.stringify(value)
    return (
      <Text key={key} fz="xs" title={text.length > 24 ? text : undefined}>
        <Text span c="dimmed" fz="xs">
          {key}:
        </Text>{' '}
        {shorten(text, 24)}
      </Text>
    )
  })
}

export function AuditPage() {
  const [action, setAction] = useState<string | null>(null)
  const [outcome, setOutcome] = useState<string | null>(null)
  const [username, setUsername] = useState('')
  const [debouncedUsername] = useDebouncedValue(username.trim(), 400)
  const [page, setPage] = useState(1)
  const params = { action, outcome, username: debouncedUsername || null, limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE }
  const log = useQuery({ queryKey: ['audit', params], queryFn: () => getAuditLog(params) })

  return (
    <Stack gap="md">
      <div>
        <Title order={1} size="h3">
          Audit log
        </Title>
        <Text size="sm" c="dimmed">
          Every login, search, case view, upload and refusal. Search text is never stored, only a keyed fingerprint.
          Reading this log is itself recorded.
        </Text>
      </div>
      <Group align="flex-end">
        <Select label="Action" placeholder="Any" data={ACTIONS} value={action} onChange={(v) => { setAction(v); setPage(1) }} clearable size="xs" w={180} />
        <Select label="Outcome" placeholder="Any" data={OUTCOMES} value={outcome} onChange={(v) => { setOutcome(v); setPage(1) }} clearable size="xs" w={150} />
        <TextInput label="Username" value={username} onChange={(e) => { setUsername(e.currentTarget.value); setPage(1) }} size="xs" w={180} />
        {log.isFetching && <Loader size="xs" />}
      </Group>
      {log.error && <ErrorAlert error={log.error} />}
      {log.data && (
        <>
          <Text size="sm" c="dimmed">
            {log.data.total} events
          </Text>
          <Table.ScrollContainer minWidth={900}>
            <Table striped verticalSpacing={4} fz="xs">
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>When</Table.Th>
                  <Table.Th>User</Table.Th>
                  <Table.Th>Action</Table.Th>
                  <Table.Th>Outcome</Table.Th>
                  <Table.Th>Target</Table.Th>
                  <Table.Th>Details</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {log.data.events.map((event) => (
                  <Table.Tr key={event.id}>
                    <Table.Td style={{ whiteSpace: 'nowrap' }}>{formatDateTime(event.occurred_at)}</Table.Td>
                    <Table.Td>{event.username ?? '—'}</Table.Td>
                    <Table.Td>{event.action}</Table.Td>
                    <Table.Td>
                      <Badge size="xs" variant={event.outcome === 'success' ? 'light' : 'filled'} color="gray" tt="none">
                        {event.outcome}
                      </Badge>
                    </Table.Td>
                    <Table.Td>
                      {event.target_id && (
                        <Tooltip label={event.target_id}>
                          <Code fz="xs">{shorten(event.target_id, 22)}</Code>
                        </Tooltip>
                      )}
                    </Table.Td>
                    <Table.Td>
                      <Details details={event.details} />
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
          {log.data.total > PAGE_SIZE && (
            <Pagination total={Math.ceil(log.data.total / PAGE_SIZE)} value={page} onChange={setPage} size="sm" />
          )}
        </>
      )}
    </Stack>
  )
}
