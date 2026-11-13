// Investigator dashboard (spec §15, §21 screen 3): today's work at a glance.

import { Alert, Anchor, Button, Grid, Group, SimpleGrid, Stack, Text } from '@mantine/core'
import { IconActivity, IconPlus, IconUserCircle } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router'
import { useAuth } from '../../auth/useAuth'
import { kh } from '../api'
import { describeNotice } from '../labels'
import { MyCaseTable } from './CasesPage'
import { EmptyState, EntryBadge, Loaded, PageHeader, Panel, Stat, When } from '../ui'

export function DashboardPage() {
  const { user } = useAuth()
  const [today] = useState(() => new Intl.DateTimeFormat('en-IN', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }).format(new Date()))
  const myCases = useQuery({ queryKey: ['kh', 'my-cases'], queryFn: () => kh.myCases() })
  const notices = useQuery({ queryKey: ['kh', 'notifications', 'recent'], queryFn: () => kh.notifications({ limit: 6 }) })
  const contributions = useQuery({ queryKey: ['kh', 'contributions'], queryFn: () => kh.myContributions() })
  const creator = ['super_admin', 'administrator', 'supervisor', 'investigator'].includes(user?.org_role ?? '')
  const stationView = ['super_admin', 'administrator', 'supervisor'].includes(user?.org_role ?? '')

  return (
    <Stack gap="md">
      <PageHeader
        eyebrow={today}
        title={`Welcome, ${user?.display_name ?? ''}`}
        actions={
          creator && (
            <Button component={Link} to="/kh/cases/new" leftSection={<IconPlus size={16} />}>
              Register a case
            </Button>
          )
        }
      />
      {user && !user.profile_updated_at && (
        <Alert color="hawk" variant="light" icon={<IconUserCircle size={18} />} title="Complete your profile">
          <Group justify="space-between" wrap="nowrap">
            <Text size="sm">Add your email and phone, so your Supervisor can reach you.</Text>
            <Button component={Link} to="/kh/profile" size="xs">
              Open my profile
            </Button>
          </Group>
        </Alert>
      )}
      {stationView && (
        <Alert color="hawk" variant="light" icon={<IconActivity size={18} />} p="xs">
          <Group justify="space-between">
            <Text size="sm">
              {user?.org_role === 'super_admin'
                ? 'You can see every police station: its open, closed and pending cases, and how each officer is getting on. The administration area shows the whole organisation.'
                : 'Follow the open, closed and pending cases of your station, and how each officer is getting on.'}
            </Text>
            <Group gap="xs">
              <Button size="xs" variant="light" component={Link} to="/kh/performance">
                Station dashboards
              </Button>
              {user?.org_role === 'super_admin' && (
                <Button size="xs" variant="subtle" component={Link} to="/kh/admin">
                  Administration overview
                </Button>
              )}
            </Group>
          </Group>
        </Alert>
      )}
      <SimpleGrid cols={{ base: 2, md: 3 }}>
        <Stat label="My cases" value={myCases.data?.length ?? '…'} hint="you are on the team" />
        <Stat label="Notes written" value={contributions.data?.totals.notes ?? '…'} hint="by you" />
        <Stat label="Exhibits added" value={contributions.data?.totals.evidence ?? '…'} hint="by you" />
      </SimpleGrid>

      <Grid gap="md">
        <Grid.Col span={{ base: 12, lg: 8 }}>
          <Stack gap="md">
            <Panel title="My cases" actions={<Anchor component={Link} to="/kh/cases" size="xs">All cases</Anchor>} p="0">
              <Loaded query={myCases}>
                {(list) =>
                  list.length === 0 ? (
                    <EmptyState title="No cases yet">Cases you lead, or are on the team of, appear here.</EmptyState>
                  ) : (
                    <MyCaseTable items={list} />
                  )
                }
              </Loaded>
            </Panel>

            <Panel title="My recent contributions" actions={<Anchor component={Link} to="/kh/contributions" size="xs">All</Anchor>}>
              <Loaded query={contributions}>
                {(data) =>
                  data.entries.length === 0 ? (
                    <Text size="sm" c="dimmed">
                      Nothing yet.
                    </Text>
                  ) : (
                    <Stack gap={6}>
                      {data.entries.slice(0, 6).map((e) => (
                        <Group key={`${e.case.id}-${e.seq}`} justify="space-between" wrap="nowrap">
                          <Group gap="xs" wrap="nowrap" style={{ minWidth: 0 }}>
                            <EntryBadge value={e.kind} />
                            <Anchor component={Link} to={`/kh/case/${e.case.id}/history#entry-${e.seq}`} size="sm" truncate>
                              {e.summary}
                            </Anchor>
                          </Group>
                          <Group gap="xs" wrap="nowrap">
                            <Text size="xs" c="dimmed" ff="monospace">
                              {e.case.display_id}
                            </Text>
                            <When at={e.at} size="xs" />
                          </Group>
                        </Group>
                      ))}
                    </Stack>
                  )
                }
              </Loaded>
            </Panel>
          </Stack>
        </Grid.Col>

        <Grid.Col span={{ base: 12, lg: 4 }}>
          <Stack gap="md">
            <Panel title="Recent notices" actions={<Anchor component={Link} to="/kh/notifications" size="xs">All</Anchor>}>
              <Loaded query={notices}>
                {(list) =>
                  list.items.length === 0 ? (
                    <Text size="sm" c="dimmed">
                      No notices.
                    </Text>
                  ) : (
                    <Stack gap={8}>
                      {list.items.map((n) => {
                        const { text, href } = describeNotice(n)
                        return (
                          <div key={n.id}>
                            {href ? (
                              <Anchor component={Link} to={href} size="sm" fw={n.read_at ? 400 : 600}>
                                {text}
                              </Anchor>
                            ) : (
                              <Text size="sm" fw={n.read_at ? 400 : 600}>
                                {text}
                              </Text>
                            )}
                            <div>
                              <When at={n.created_at} size="xs" />
                            </div>
                          </div>
                        )
                      })}
                    </Stack>
                  )
                }
              </Loaded>
            </Panel>
          </Stack>
        </Grid.Col>
      </Grid>
    </Stack>
  )
}
