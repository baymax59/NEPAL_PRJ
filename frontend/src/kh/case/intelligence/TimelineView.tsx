// The reconstructed timeline of the case, and rebuilding it (a new version of the timeline note, recorded in the history).

import { Alert, Badge, Button, Group, List, Paper, Stack, Text, Timeline } from '@mantine/core'
import { IconCalendarEvent, IconFileText, IconRefresh, IconUsersGroup } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { kh } from '../../api'
import { toastDone, toastError, useOnceKey } from '../../feedback'
import type { CaseDetail } from '../../types'
import { EmptyState, EntryNumber, Loaded, Panel, PersonName, When } from '../../ui'
import { formatDay } from '../../time'
import { useRefreshCase } from '../helpers'
import { SourceLink } from './common'
import { pageText } from './format'

const KIND: Record<string, string> = {
  dated_mention: 'from the text',
  order_under_appeal: 'order under appeal',
  evidence_collected: 'exhibit collected',
  official_reference: 'official reference',
  imported_finding: 'imported finding',
}

export function TimelineView({ detail }: { detail: CaseDetail }) {
  const client = useQueryClient()
  const refresh = useRefreshCase(detail.id)
  const [key, renew] = useOnceKey()
  const query = useQuery({ queryKey: ['kh', 'case', detail.id, 'ci', 'timeline'], queryFn: () => kh.timeline(detail.id) })
  const writable = detail.can.add_files
  const rebuild = useMutation({
    mutationFn: () => kh.rebuildTimeline(detail.id, { message: null }, key),
    onSuccess: (built) => {
      renew()
      refresh()
      client.invalidateQueries({ queryKey: ['kh', 'case', detail.id, 'ci'] })
      toastDone(`Timeline version ${built.version_number} saved: ${built.events} dated entries`)
    },
    onError: (error) => toastError(error, 'Timeline not rebuilt'),
  })
  const action = writable ? (
    <Button size="xs" leftSection={<IconRefresh size={14} />} loading={rebuild.isPending} onClick={() => rebuild.mutate()}>
      {query.data?.timeline ? 'Rebuild the timeline' : 'Build the timeline'}
    </Button>
  ) : undefined
  return (
    <Loaded query={query}>
      {({ timeline }) =>
        !timeline ? (
          <Paper withBorder pb="md">
            <EmptyState title="No timeline yet" icon={<IconCalendarEvent size={22} />}>
              Case Intelligence can build a timeline from the dates written in the case's documents and notes, and the dates the records hold (when exhibits
              were collected, official references). It is saved as a note in the case, built only from what every member may see, and every rebuild is a new version.
            </EmptyState>
            <Stack align="center">
              {action ?? (
                <Text size="xs" c="dimmed">
                  Only people who can add to the case can build it.
                </Text>
              )}
            </Stack>
          </Paper>
        ) : (
          <Stack gap="md">
            <Panel
              title={
                <Group gap={6}>
                  <Text fw={600}>Reconstructed timeline</Text>
                  <Text ff="monospace" size="sm" c="dimmed">
                    {timeline.display_id} · version {timeline.version_number} of {timeline.versions}
                  </Text>
                </Group>
              }
              actions={action}
            >
              <Stack gap="sm">
                <Group gap={6} wrap="wrap">
                  <Text size="xs" c="dimmed">
                    Built from the case as of <EntryNumber seq={timeline.based_on_entry} caseId={detail.id} /> by
                  </Text>
                  <PersonName person={timeline.author} size="xs" />
                  <When at={timeline.created_at} size="xs" />
                </Group>
                {timeline.shared_view && (
                  <Alert color="gray" variant="light" p="xs" icon={<IconUsersGroup size={16} />}>
                    <Text size="xs">{timeline.shared_view}</Text>
                  </Alert>
                )}
                <Timeline bulletSize={18} lineWidth={2} color="hawk">
                  {timeline.events.map((event, i) => (
                    <Timeline.Item
                      key={`${event.date}-${i}`}
                      bullet={event.method === 'record' ? <IconFileText size={11} /> : undefined}
                      title={
                        <Group gap={6} wrap="wrap">
                          <Text size="sm" fw={600} ff="monospace">
                            {formatDay(event.date)}
                          </Text>
                          <Badge size="xs" variant="light" color={event.method === 'record' ? 'grape' : 'hawk'}>
                            {KIND[event.kind] ?? event.kind}
                          </Badge>
                          {event.source.kind === 'record' ? (
                            <Text size="xs" c="dimmed">
                              {event.source.display_id}
                            </Text>
                          ) : (
                            <SourceLink caseId={detail.id} source={event.source} pages={event.page ? pageText(event.page, event.page) : undefined} />
                          )}
                        </Group>
                      }
                    >
                      <Text size="sm">{event.description}</Text>
                      {event.date_text && (
                        <Text size="xs" c="dimmed">
                          Written as “{event.date_text}”
                        </Text>
                      )}
                    </Timeline.Item>
                  ))}
                </Timeline>
              </Stack>
            </Panel>
            <Panel title="How it was built">
              <Stack gap="xs">
                <Text size="xs">{timeline.method}</Text>
                <Text size="xs" fw={600}>
                  Used ({timeline.sources_used.length})
                </Text>
                <Group gap={6} wrap="wrap">
                  {timeline.sources_used.map((s) => (
                    <Badge key={s.display_id} variant="outline" color="gray" size="sm">
                      {s.display_id} v{s.version_number}: {s.events} entr{s.events === 1 ? 'y' : 'ies'}
                    </Badge>
                  ))}
                </Group>
                {timeline.not_used.length > 0 && (
                  <>
                    <Text size="xs" fw={600}>
                      Not used ({timeline.not_used.length})
                    </Text>
                    <List size="xs" spacing={2}>
                      {timeline.not_used.map((n) => (
                        <List.Item key={n.display_id}>
                          {n.display_id}: {n.reason}
                        </List.Item>
                      ))}
                    </List>
                  </>
                )}
              </Stack>
            </Panel>
          </Stack>
        )
      }
    </Loaded>
  )
}
