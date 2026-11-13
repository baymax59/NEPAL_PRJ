// My cases (the cases a person is on the team of) and all the cases a user can open (spec §15).

import { Anchor, Badge, Button, Group, Paper, Select, Stack, Table, Tabs, Text, TextInput } from '@mantine/core'
import { useDebouncedValue } from '@mantine/hooks'
import { IconPlus, IconSearch } from '@tabler/icons-react'
import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router'
import { useAuth } from '../../auth/useAuth'
import { kh } from '../api'
import { roleLabel, WORKFLOW_STATUSES, workflowLook } from '../labels'
import type { MyCase } from '../types'
import { ClassificationBadge, EmptyState, Loaded, PageHeader, PriorityBadge, When, WorkflowBadge } from '../ui'
import { formatDay } from '../time'

export function MyCaseTable({ items }: { items: MyCase[] }) {
  return (
    <Table>
      <Table.Thead>
        <Table.Tr>
          <Table.Th>Case</Table.Th>
          <Table.Th>Your part</Table.Th>
          <Table.Th>Status</Table.Th>
          <Table.Th>Priority</Table.Th>
          <Table.Th>Classification</Table.Th>
          <Table.Th>Last activity</Table.Th>
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {items.map((m) => (
          <Table.Tr key={m.case.id}>
            <Table.Td>
              <Anchor component={Link} to={`/kh/case/${m.case.id}`} size="sm" fw={500}>
                {m.case.title}
              </Anchor>
              <Text size="xs" c="dimmed" ff="monospace">
                {m.case.display_id}
              </Text>
            </Table.Td>
            <Table.Td>
              <Text size="sm">{roleLabel(m.role)}</Text>
            </Table.Td>
            <Table.Td>
              <WorkflowBadge value={m.case.workflow_status} />
            </Table.Td>
            <Table.Td>
              <PriorityBadge value={m.case.priority} />
            </Table.Td>
            <Table.Td>
              <ClassificationBadge value={m.case.classification} />
            </Table.Td>
            <Table.Td>
              <When at={m.last_activity ?? m.active_from} size="xs" />
            </Table.Td>
          </Table.Tr>
        ))}
      </Table.Tbody>
    </Table>
  )
}

export function CasesPage() {
  const { user } = useAuth()
  const mine = useQuery({ queryKey: ['kh', 'my-cases'], queryFn: () => kh.myCases() })
  const [q, setQ] = useState('')
  const [status, setStatus] = useState<string | null>(null)
  const [debounced] = useDebouncedValue(q, 300)
  const all = useInfiniteQuery({
    queryKey: ['kh', 'cases', 'list', debounced, status],
    queryFn: ({ pageParam }) => kh.cases({ q: debounced || undefined, workflow_status: status, limit: 50, cursor: pageParam }),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
  })
  const cases = all.data?.pages.flatMap((p) => p.items) ?? []
  return (
    <Stack gap="md">
      <PageHeader
        eyebrow="Investigation"
        title="My cases"
        actions={
          ['super_admin', 'administrator', 'supervisor', 'investigator'].includes(user?.org_role ?? '') && (
            <Button component={Link} to="/kh/cases/new" leftSection={<IconPlus size={16} />}>
              Register a case
            </Button>
          )
        }
      >
        <Text size="sm" c="dimmed">
          The cases you are on the team of: as the Investigator who leads them, or as a Sub Investigator, Analyst or Viewer.
        </Text>
      </PageHeader>
      <Tabs defaultValue="mine">
        <Tabs.List>
          <Tabs.Tab value="mine">
            My cases <Badge size="xs" color="gray" circle>{mine.data?.length ?? 0}</Badge>
          </Tabs.Tab>
          <Tabs.Tab value="all">All cases I can open</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="mine" pt="md">
          <Loaded query={mine}>
            {(list) =>
              list.length === 0 ? (
                <Paper withBorder>
                  <EmptyState title="No cases yet">When you are given a case, or added to a team, it appears here.</EmptyState>
                </Paper>
              ) : (
                <Paper withBorder radius="sm">
                  <MyCaseTable items={list} />
                </Paper>
              )
            }
          </Loaded>
        </Tabs.Panel>
        <Tabs.Panel value="all" pt="md">
          <Stack gap="sm">
            <Group gap="sm">
              <TextInput leftSection={<IconSearch size={14} />} placeholder="Case ID or title" value={q} onChange={(e) => setQ(e.currentTarget.value)} w={300} size="xs" />
              <Select
                size="xs"
                w={220}
                placeholder="Any status"
                data={WORKFLOW_STATUSES.map((s) => ({ value: s, label: workflowLook(s).label }))}
                value={status}
                onChange={setStatus}
                clearable
              />
            </Group>
            <Paper withBorder radius="sm">
              {cases.length === 0 && !all.isPending ? (
                <EmptyState title="No cases found" />
              ) : (
                <Table>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Case</Table.Th>
                      <Table.Th>Type</Table.Th>
                      <Table.Th>Official reference</Table.Th>
                      <Table.Th>Status</Table.Th>
                      <Table.Th>Priority</Table.Th>
                      <Table.Th>Registered</Table.Th>
                      <Table.Th>Your part</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {cases.map((c) => (
                      <Table.Tr key={c.id}>
                        <Table.Td>
                          <Anchor component={Link} to={`/kh/case/${c.id}`} size="sm" fw={500}>
                            {c.title}
                          </Anchor>
                          <Text size="xs" c="dimmed" ff="monospace">
                            {c.display_id}
                          </Text>
                        </Table.Td>
                        <Table.Td>
                          <Text size="xs">{c.case_type_label}</Text>
                        </Table.Td>
                        <Table.Td>
                          <Text size="xs">{c.official_references.join(', ') || '—'}</Text>
                        </Table.Td>
                        <Table.Td>
                          <WorkflowBadge value={c.workflow_status} />
                        </Table.Td>
                        <Table.Td>
                          <PriorityBadge value={c.priority} />
                        </Table.Td>
                        <Table.Td>
                          <Text size="xs" c="dimmed">
                            {formatDay(c.created_at)}
                          </Text>
                        </Table.Td>
                        <Table.Td>
                          <Text size="xs" c={c.my_role ? undefined : 'dimmed'}>
                            {c.my_role ? roleLabel(c.my_role) : 'oversight only'}
                          </Text>
                        </Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              )}
            </Paper>
            {all.hasNextPage && (
              <Button variant="default" size="xs" onClick={() => all.fetchNextPage()} loading={all.isFetchingNextPage}>
                More
              </Button>
            )}
          </Stack>
        </Tabs.Panel>
      </Tabs>
    </Stack>
  )
}
