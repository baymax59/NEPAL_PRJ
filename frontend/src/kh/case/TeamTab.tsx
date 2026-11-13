// The team: who works on the case, added straight in (no invitation, no approval), and the permanent access history.

import { Badge, Button, Group, Stack, Table, Text, Timeline } from '@mantine/core'
import { IconArrowsExchange, IconUserMinus, IconUserPlus } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useAuth } from '../../auth/useAuth'
import { kh } from '../api'
import { toastDone, toastError } from '../feedback'
import { roleLabel } from '../labels'
import { formatWhen } from '../time'
import type { TeamMemberOut } from '../types'
import { ConfirmModal, Loaded, Panel, PersonName } from '../ui'
import { useCase } from './context'
import { AddMemberDialog, HandOverDialog } from './dialogs'

export function TeamTab() {
  const detail = useCase()
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [dialog, setDialog] = useState<null | 'add' | 'handover'>(null)
  const [removing, setRemoving] = useState<TeamMemberOut | null>(null)
  const team = useQuery({ queryKey: ['kh', 'case', detail.id, 'team'], queryFn: () => kh.team(detail.id) })
  const history = useQuery({ queryKey: ['kh', 'case', detail.id, 'access-history'], queryFn: () => kh.accessHistory(detail.id) })
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['kh', 'case', detail.id] })
  const remove = useMutation({
    mutationFn: ({ member, reason }: { member: TeamMemberOut; reason: string }) => kh.removeMember(detail.id, member.user!.id, reason),
    onSuccess: () => {
      toastDone('Taken off the team. Their earlier work stays credited to them.')
      refresh()
      setRemoving(null)
    },
    onError: (error) => toastError(error),
  })

  return (
    <Stack gap="md">
      <Group justify="space-between">
        <Text size="sm" c="dimmed">
          Who works on {detail.display_id}, and since when. Taking someone off the team never removes what they did.
        </Text>
        <Group gap="xs">
          {detail.can.hand_over && (
            <Button size="xs" variant="default" leftSection={<IconArrowsExchange size={14} />} onClick={() => setDialog('handover')}>
              Hand over the case
            </Button>
          )}
          {detail.can.manage_team && (
            <Button size="xs" leftSection={<IconUserPlus size={14} />} onClick={() => setDialog('add')}>
              Add team member
            </Button>
          )}
        </Group>
      </Group>

      <Panel title="Members" p="0">
        <Loaded query={team}>
          {(view) => (
            <Table>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Person</Table.Th>
                  <Table.Th>Part in the case</Table.Th>
                  <Table.Th>Added</Table.Th>
                  <Table.Th>Status</Table.Th>
                  <Table.Th />
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {view.team.map((m, i) => {
                  const active = !m.revoked_at
                  return (
                    <Table.Tr key={`${m.user?.id}-${i}`} style={{ opacity: active ? 1 : 0.55 }}>
                      <Table.Td>
                        <PersonName person={m.user} />
                      </Table.Td>
                      <Table.Td>
                        <Text size="sm">{roleLabel(m.role)}</Text>
                      </Table.Td>
                      <Table.Td>
                        <Text size="xs" c="dimmed">
                          {formatWhen(m.granted_at)}
                          {m.granted_by ? ` by ${m.granted_by.display_name}` : ''}
                        </Text>
                      </Table.Td>
                      <Table.Td>
                        {active ? (
                          <Badge size="sm" color="green">
                            On the team
                          </Badge>
                        ) : (
                          <Text size="xs" c="dimmed">
                            Left {formatWhen(m.revoked_at)}
                            {m.revoked_by ? ` (by ${m.revoked_by.display_name})` : ''}
                          </Text>
                        )}
                      </Table.Td>
                      <Table.Td>
                        {detail.can.manage_team && active && m.role !== 'lead' && m.user?.id !== user?.id && (
                          <Button size="compact-xs" variant="subtle" color="orange" leftSection={<IconUserMinus size={13} />} onClick={() => setRemoving(m)}>
                            Take off the team
                          </Button>
                        )}
                      </Table.Td>
                    </Table.Tr>
                  )
                })}
              </Table.Tbody>
            </Table>
          )}
        </Loaded>
      </Panel>

      <Panel title="Access history (permanent)">
        <Loaded query={history}>
          {(events) =>
            events.length === 0 ? (
              <Text size="sm" c="dimmed">
                No changes yet.
              </Text>
            ) : (
              <Timeline bulletSize={14} lineWidth={2}>
                {events.map((e) => (
                  <Timeline.Item key={e.id} color={e.change === 'membership_granted' ? 'green' : 'orange'}>
                    <Text size="sm">
                      <b>{e.user?.display_name ?? 'Someone'}</b> {e.change === 'membership_granted' ? `became ${roleLabel(e.new_value)}` : `stopped being ${roleLabel(e.old_value)}`}
                    </Text>
                    <Text size="xs" c="dimmed">
                      {formatWhen(e.at)} · by {e.actor?.display_name ?? 'the system'}
                      {e.reason ? ` · “${e.reason}”` : ''}
                    </Text>
                  </Timeline.Item>
                ))}
              </Timeline>
            )
          }
        </Loaded>
      </Panel>

      {dialog === 'add' && <AddMemberDialog opened onClose={() => setDialog(null)} detail={detail} />}
      {dialog === 'handover' && <HandOverDialog opened onClose={() => setDialog(null)} detail={detail} />}
      <ConfirmModal
        opened={removing !== null}
        onClose={() => setRemoving(null)}
        title={`Take ${removing?.user?.display_name ?? ''} off the team?`}
        confirmLabel="Take off the team"
        color="orange"
        reason="required"
        loading={remove.isPending}
        onConfirm={(reason) => removing && remove.mutate({ member: removing, reason })}
      >
        <Text size="sm">
          They can't open {detail.display_id} from their next request. Everything they added stays in the history, credited to them.
        </Text>
      </ConfirmModal>
    </Stack>
  )
}
