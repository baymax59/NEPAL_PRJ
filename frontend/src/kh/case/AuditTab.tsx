// The case's audit trail (spec §21 screen 20), for administrators: every request about the case, including refusals.

import { Badge, Button, Code, Group, Paper, SegmentedControl, Stack, Table, Text, Tooltip } from '@mantine/core'
import { useInfiniteQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { kh } from '../api'
import { EmptyState } from '../ui'
import { formatWhen } from '../time'
import { useCase } from './context'

const OUTCOME_COLOR: Record<string, string> = { success: 'green', denied: 'red', not_found: 'gray', rejected: 'orange', error: 'red' }

export function CaseAuditTrail({ caseId }: { caseId: string }) {
  // Every read is recorded too, so the refusals are also offered on their own (CM-8).
  const [show, setShow] = useState<'all' | 'refused'>('all')
  const query = useInfiniteQuery({
    queryKey: ['kh', 'admin', 'audit', caseId, show],
    queryFn: ({ pageParam }) => kh.caseAudit(caseId, { limit: 100, cursor: pageParam, show }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
  })
  const items = query.data?.pages.flatMap((p) => p.items) ?? []
  const total = query.data?.pages[0]?.total ?? 0
  return (
    <Stack gap="sm">
      <Group justify="space-between" wrap="wrap">
        <Text size="sm" c="dimmed">
          {show === 'all'
            ? `${total} events. Recorded for every request about the case, including refused ones (deletions, rewrites, access to what someone may not see).`
            : `${total} refused or denied requests: deletions, history rewrites, access to what someone may not see, changes the rules forbid.`}
        </Text>
        <SegmentedControl
          size="xs"
          value={show}
          onChange={(value) => setShow(value as 'all' | 'refused')}
          data={[
            { value: 'all', label: 'Everything' },
            { value: 'refused', label: 'Refused and denied' },
          ]}
        />
      </Group>
      {items.length === 0 && !query.isPending ? (
        <EmptyState title="No events" />
      ) : (
        <Paper withBorder radius="sm">
          <Table>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>When</Table.Th>
                <Table.Th>Who</Table.Th>
                <Table.Th>Action</Table.Th>
                <Table.Th>Outcome</Table.Th>
                <Table.Th>About</Table.Th>
                <Table.Th>Details</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {items.map((e) => (
                <Table.Tr key={e.id}>
                  <Table.Td>
                    <Text size="xs" style={{ whiteSpace: 'nowrap' }}>
                      {formatWhen(e.occurred_at)}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    <Text size="xs">{e.username ?? '—'}</Text>
                  </Table.Td>
                  <Table.Td>
                    <Code fz="xs">{e.action}</Code>
                  </Table.Td>
                  <Table.Td>
                    <Badge size="xs" color={OUTCOME_COLOR[e.outcome] ?? 'gray'}>
                      {e.outcome.replace('_', ' ')}
                    </Badge>
                  </Table.Td>
                  <Table.Td>
                    <Text size="xs" ff="monospace">
                      {e.target_id ?? ''}
                    </Text>
                  </Table.Td>
                  <Table.Td>
                    {Object.keys(e.details ?? {}).length > 0 && (
                      <Tooltip label={<pre style={{ margin: 0, fontSize: 11 }}>{JSON.stringify(e.details, null, 2)}</pre>} multiline maw={420}>
                        <Text size="xs" c="dimmed" truncate maw={260}>
                          {Object.entries(e.details)
                            .map(([k, v]) => `${k}: ${typeof v === 'object' ? JSON.stringify(v) : String(v)}`)
                            .join(' · ')}
                        </Text>
                      </Tooltip>
                    )}
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Paper>
      )}
      {query.hasNextPage && (
        <Group justify="center">
          <Button size="xs" variant="default" onClick={() => query.fetchNextPage()} loading={query.isFetchingNextPage}>
            Older events
          </Button>
        </Group>
      )}
    </Stack>
  )
}

export function AuditTab() {
  const detail = useCase()
  return <CaseAuditTrail caseId={detail.id} />
}
