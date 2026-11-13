// The investigator's own lists (spec §15): notifications and contributions.

import { Alert, Anchor, Button, Group, Paper, SegmentedControl, SimpleGrid, Stack, Table, Text } from '@mantine/core'
import { IconBell, IconChecks } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { kh } from '../api'
import { toastDone } from '../feedback'
import { describeNotice } from '../labels'
import { EmptyState, EntryBadge, EntryNumber, Loaded, PageHeader, Panel, Stat, When } from '../ui'

// ------------------------------------------------------------------ notifications

export function NotificationsPage() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [show, setShow] = useState('all')
  const query = useQuery({ queryKey: ['kh', 'notifications', show], queryFn: () => kh.notifications({ limit: 100, unread_only: show === 'unread' ? 'true' : undefined }) })
  const readOne = useMutation({ mutationFn: (id: number) => kh.readNotification(id), onSuccess: () => queryClient.invalidateQueries({ queryKey: ['kh', 'notifications'] }) })
  const readAll = useMutation({
    mutationFn: () => kh.readAllNotifications(),
    onSuccess: (r) => {
      toastDone(`${r.marked} marked as read`)
      queryClient.invalidateQueries({ queryKey: ['kh', 'notifications'] })
    },
  })
  return (
    <Stack gap="md">
      <PageHeader
        eyebrow="Investigation"
        title="Notifications"
        actions={
          <Button size="xs" variant="default" leftSection={<IconChecks size={14} />} onClick={() => readAll.mutate()} loading={readAll.isPending}>
            Mark all as read
          </Button>
        }
      >
        <Text size="sm" c="dimmed">
          New notices arrive live while Knight Hawk is open.
        </Text>
      </PageHeader>
      <SegmentedControl size="xs" value={show} onChange={setShow} data={[{ value: 'all', label: 'All' }, { value: 'unread', label: 'Unread' }]} w={200} />
      <Loaded query={query}>
        {(list) =>
          list.items.length === 0 ? (
            <Paper withBorder>
              <EmptyState title="No notices" icon={<IconBell size={22} />} />
            </Paper>
          ) : (
            <Paper withBorder radius="sm">
              {list.items.map((n, i) => {
                const { text, href } = describeNotice(n)
                return (
                  <Group
                    key={n.id}
                    justify="space-between"
                    wrap="nowrap"
                    px="sm"
                    py={10}
                    style={{ borderTop: i ? '1px solid var(--mantine-color-default-border)' : undefined, background: n.read_at ? undefined : 'var(--mantine-color-hawk-light)' }}
                  >
                    <Group gap="sm" wrap="nowrap" style={{ minWidth: 0 }}>
                      {!n.read_at && <span style={{ width: 8, height: 8, borderRadius: 8, background: 'var(--mantine-color-hawk-4)', flex: 'none' }} />}
                      <Text
                        size="sm"
                        style={{ cursor: href ? 'pointer' : 'default' }}
                        onClick={() => {
                          if (!n.read_at) readOne.mutate(n.id)
                          if (href) navigate(href)
                        }}
                      >
                        {text}
                      </Text>
                    </Group>
                    <Group gap="xs" wrap="nowrap">
                      <When at={n.created_at} size="xs" />
                      {!n.read_at && (
                        <Button size="compact-xs" variant="subtle" onClick={() => readOne.mutate(n.id)}>
                          Mark read
                        </Button>
                      )}
                    </Group>
                  </Group>
                )
              })}
            </Paper>
          )
        }
      </Loaded>
    </Stack>
  )
}

// ------------------------------------------------------------------ contributions

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`

export function ContributionsPage() {
  const query = useQuery({ queryKey: ['kh', 'contributions'], queryFn: () => kh.myContributions() })
  return (
    <Stack gap="md">
      <PageHeader eyebrow="Investigation" title="My contributions">
        <Text size="sm" c="dimmed">
          What you did in the cases you can open. Everything you did stays credited to you, permanently.
        </Text>
      </PageHeader>
      <Loaded query={query}>
        {(data) => (
          <Stack gap="md">
            <SimpleGrid cols={{ base: 2, sm: 4 }}>
              <Stat label="History entries" value={data.totals.entries} />
              <Stat label="Notes written" value={data.totals.notes} />
              <Stat label="New versions" value={data.totals.revisions} />
              <Stat label="Exhibits added" value={data.totals.evidence} />
            </SimpleGrid>
            {Object.values(data.no_longer_open).some((n) => n > 0) && (
              <Alert color="gray" variant="light" title="Also credited to you, in cases you can no longer open">
                <Text size="sm">
                  {[
                    plural(data.no_longer_open.entries, 'entry'),
                    plural(data.no_longer_open.notes, 'note'),
                    plural(data.no_longer_open.evidence, 'exhibit'),
                  ].join(', ')}
                  , for example in a case you were taken off. They stay credited to you permanently; nothing from those cases is shown here. Your supervisor or an
                  administrator can show them to you.
                </Text>
              </Alert>
            )}
            <Panel title="Recent entries" p="0">
              {data.entries.length === 0 ? (
                <EmptyState title="No entries yet" />
              ) : (
                <Table>
                  <Table.Tbody>
                    {data.entries.map((e) => (
                      <Table.Tr key={`${e.case.id}-${e.seq}`}>
                        <Table.Td>
                          <Group gap="xs" wrap="nowrap">
                            <EntryBadge value={e.kind} />
                            <Text size="sm">{e.summary}</Text>
                          </Group>
                          <Text size="xs" c="dimmed">
                            <Anchor component={Link} to={`/kh/case/${e.case.id}`} size="xs" ff="monospace">
                              {e.case.display_id}
                            </Anchor>{' '}
                            · {e.case.title}
                          </Text>
                        </Table.Td>
                        <Table.Td>
                          <EntryNumber seq={e.seq} caseId={e.case.id} />
                        </Table.Td>
                        <Table.Td>
                          <When at={e.at} size="xs" />
                        </Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              )}
            </Panel>
          </Stack>
        )}
      </Loaded>
    </Stack>
  )
}
