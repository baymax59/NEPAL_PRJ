// The case's history: one plain list, oldest first, of everything that happened (entry 1, 2, 3...), and its check.

import { Alert, Button, Group, Paper, Stack, Table, Text } from '@mantine/core'
import { IconShieldCheck, IconShieldX } from '@tabler/icons-react'
import { useInfiniteQuery, useMutation } from '@tanstack/react-query'
import { kh } from '../api'
import { toastError } from '../feedback'
import { EmptyState, EntryBadge, Loaded, PersonName, When } from '../ui'
import { useCase } from './context'

const PAGE = 100

export function HistoryTab() {
  const detail = useCase()
  const query = useInfiniteQuery({
    queryKey: ['kh', 'case', detail.id, 'history'],
    queryFn: ({ pageParam }) => kh.history(detail.id, { limit: PAGE, after: pageParam }),
    initialPageParam: undefined as number | undefined,
    getNextPageParam: (last) => last.next_after ?? undefined,
  })
  const check = useMutation({ mutationFn: () => kh.historyCheck(detail.id), onError: (error) => toastError(error, 'The check could not be made') })
  const entries = query.data?.pages.flatMap((p) => p.entries) ?? []

  return (
    <Stack gap="sm">
      <Group justify="space-between" wrap="wrap" gap="xs">
        <Text size="sm" c="dimmed">
          Everything that happened in {detail.display_id}, in order. Each entry is tied to the one before it, so none can be changed, removed or moved without it being found.
        </Text>
        <Button size="xs" variant="default" leftSection={<IconShieldCheck size={14} />} loading={check.isPending} onClick={() => check.mutate()}>
          Check the history
        </Button>
      </Group>

      {check.data &&
        (check.data.intact ? (
          <Alert color="green" icon={<IconShieldCheck size={18} />} p="xs" title="History is intact">
            <Text size="sm">All {check.data.entries} entries were checked: each one is as it was written and follows the one before it.</Text>
          </Alert>
        ) : (
          <Alert color="red" icon={<IconShieldX size={18} />} p="xs" title="The history does not check out">
            <Text size="sm">
              The first problem is at entry {check.data.first_problem}: {check.data.problem}. Tell your supervisor and an administrator now.
            </Text>
          </Alert>
        ))}

      <Loaded query={query}>
        {() =>
          entries.length === 0 ? (
            <EmptyState title="No entries yet" />
          ) : (
            <Paper withBorder radius="sm">
              <Table>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th w={80}>Entry</Table.Th>
                    <Table.Th>What happened</Table.Th>
                    <Table.Th>By</Table.Th>
                    <Table.Th>When</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {entries.map((entry) => (
                    <Table.Tr key={entry.seq} id={`entry-${entry.seq}`}>
                      <Table.Td>
                        <Text size="sm" fw={600}>
                          {entry.seq}
                        </Text>
                      </Table.Td>
                      <Table.Td>
                        <Group gap="xs" wrap="nowrap">
                          <EntryBadge value={entry.kind} />
                          <Text size="sm">{entry.summary}</Text>
                        </Group>
                      </Table.Td>
                      <Table.Td>
                        <PersonName person={entry.actor} size="xs" />
                      </Table.Td>
                      <Table.Td>
                        <When at={entry.at} size="xs" />
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
              {query.hasNextPage && (
                <Group justify="center" p="sm">
                  <Button size="xs" variant="default" loading={query.isFetchingNextPage} onClick={() => query.fetchNextPage()}>
                    Show more entries
                  </Button>
                </Group>
              )}
            </Paper>
          )
        }
      </Loaded>
    </Stack>
  )
}
