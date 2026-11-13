import {
  ActionIcon,
  AppShell,
  Center,
  Loader,
  Badge,
  Box,
  Burger,
  Container,
  Divider,
  Group,
  Indicator,
  Menu,
  NavLink,
  ScrollArea,
  Text,
  Tooltip,
  UnstyledButton,
  useComputedColorScheme,
  useMantineColorScheme,
} from '@mantine/core'
import { useDisclosure } from '@mantine/hooks'
import {
  IconActivity,
  IconBell,
  IconBriefcase,
  IconFileUpload,
  IconFingerprint,
  IconPlugConnected,
  IconFileCertificate,
  IconShieldLock,
  IconUserCircle,
  IconHistory,
  IconLayoutDashboard,
  IconListSearch,
  IconLogout,
  IconMoon,
  IconPlus,
  IconShieldCheck,
  IconSitemap,
  IconSun,
  IconChartBar,
  IconUsers,
  IconUserStar,
} from '@tabler/icons-react'
import { Suspense, type ReactNode } from 'react'
import { Link, Outlet, useLocation, useNavigate } from 'react-router'
import { useAuth } from '../auth/useAuth'
import { Brand } from '../kh/Brand'
import { UserAvatar } from './UserAvatar'
import { roleLabel } from '../kh/labels'
import { useLiveNotices, watchFor } from '../kh/live'

interface Item {
  to: string
  label: string
  icon: ReactNode
  exact?: boolean
  badge?: number | null
}

function Section({ title, items, onNavigate }: { title: string; items: Item[]; onNavigate: () => void }) {
  const { pathname } = useLocation()
  return (
    <Box mb="sm">
      <Text size="10px" fw={700} c="dimmed" tt="uppercase" px="sm" mb={4} style={{ letterSpacing: 1 }}>
        {title}
      </Text>
      {items.map((item) => {
        const active = item.exact ? pathname === item.to : pathname === item.to || pathname.startsWith(`${item.to}/`)
        return (
          <NavLink
            key={item.to}
            component={Link}
            to={item.to}
            label={item.label}
            leftSection={item.icon}
            active={active}
            onClick={onNavigate}
            rightSection={item.badge ? <Badge size="xs" circle color="red">{item.badge > 99 ? '99+' : item.badge}</Badge> : null}
            styles={{ root: { borderRadius: 4 }, label: { fontSize: 13 } }}
            py={6}
          />
        )
      })}
    </Box>
  )
}

const CREATORS = ['super_admin', 'administrator', 'supervisor', 'investigator']

export function AppLayout() {
  const { user, logout, hasRole } = useAuth()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const [opened, { toggle, close }] = useDisclosure()
  const { setColorScheme } = useMantineColorScheme()
  const scheme = useComputedColorScheme('dark')
  const isAdmin = user?.org_role === 'super_admin'
  // The open page stays current while colleagues work (live.ts): the stream is told which page this is.
  const watch = watchFor(pathname)
  const live = useLiveNotices(user !== null, watch === 'admin' && !isAdmin ? null : watch)
  const inKnightHawk = pathname.startsWith('/kh')
  const icon = (node: ReactNode) => <Box c="dimmed" style={{ display: 'flex' }}>{node}</Box>

  const investigation: Item[] = [
    { to: '/kh', label: 'Dashboard', icon: icon(<IconLayoutDashboard size={16} />), exact: true },
    { to: '/kh/cases', label: 'My cases', icon: icon(<IconBriefcase size={16} />) },
    { to: '/kh/notifications', label: 'Notifications', icon: icon(<IconBell size={16} />), badge: live.unread },
    { to: '/kh/contributions', label: 'My contributions', icon: icon(<IconUserStar size={16} />) },
    { to: '/kh/verify-report', label: 'Check a report file', icon: icon(<IconFileCertificate size={16} />) },
    ...(user && CREATORS.includes(user.org_role) ? [{ to: '/kh/people', label: 'People & stations', icon: icon(<IconUsers size={16} />) }] : []),
    ...(user && CREATORS.includes(user.org_role)
      ? [{ to: '/kh/performance', label: user.org_role === 'investigator' ? 'My performance' : 'Station dashboards', icon: icon(<IconChartBar size={16} />) }]
      : []),
  ]
  const administration: Item[] = [
    { to: '/kh/admin', label: 'Overview', icon: icon(<IconActivity size={16} />), exact: true },
    { to: '/kh/admin/cases', label: 'All cases', icon: icon(<IconSitemap size={16} />) },
    { to: '/kh/admin/evidence', label: 'Evidence integrity', icon: icon(<IconFingerprint size={16} />) },
    { to: '/kh/admin/integrations', label: 'Integration sources', icon: icon(<IconPlugConnected size={16} />) },
    { to: '/kh/admin/activity', label: 'Investigation activity', icon: icon(<IconHistory size={16} />) },
    { to: '/audit', label: 'Audit logs', icon: icon(<IconShieldCheck size={16} />) },
  ]
  const intelligence: Item[] = [
    { to: '/', label: 'Similar-case search', icon: icon(<IconListSearch size={16} />), exact: true },
    ...(hasRole('analyst', 'admin') ? [{ to: '/new', label: 'Compare a new case', icon: icon(<IconFileUpload size={16} />) }] : []),
  ]

  return (
    <AppShell header={{ height: 52 }} navbar={{ width: 236, breakpoint: 'sm', collapsed: { mobile: !opened } }} padding="md">
      <AppShell.Header className="no-print">
        <Group h="100%" px="md" justify="space-between" wrap="nowrap">
          <Group gap="sm" wrap="nowrap">
            <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="sm" aria-label="Menu" />
            <UnstyledButton component={Link} to="/kh" aria-label="Knight Hawk dashboard">
              <Brand />
            </UnstyledButton>
          </Group>
          <Group gap={6} wrap="nowrap">
            <Tooltip label={live.status === 'live' ? 'Notices update live' : 'Reconnecting to live notices…'}>
              <Indicator color="red" size={16} label={live.unread || undefined} disabled={!live.unread} offset={4}>
                <ActionIcon variant="subtle" size="lg" component={Link} to="/kh/notifications" aria-label="Notifications">
                  <IconBell size={19} stroke={1.6} color={live.status === 'live' ? undefined : 'var(--mantine-color-dimmed)'} />
                </ActionIcon>
              </Indicator>
            </Tooltip>
            <ActionIcon
              variant="subtle"
              size="lg"
              onClick={() => setColorScheme(scheme === 'dark' ? 'light' : 'dark')}
              aria-label={scheme === 'dark' ? 'Use light mode' : 'Use dark mode'}
            >
              {scheme === 'dark' ? <IconSun size={18} /> : <IconMoon size={18} />}
            </ActionIcon>
            <Menu position="bottom-end" width={240} shadow="md">
              <Menu.Target>
                <UnstyledButton px={6} py={4} style={{ borderRadius: 4 }} aria-label="Account">
                  <Group gap={8} wrap="nowrap">
                    {user && <UserAvatar id={user.id} name={user.display_name} version={user.photo_updated_at ?? null} size={30} />}
                    <Box visibleFrom="sm" ta="right">
                      <Text size="sm" fw={500} lh={1.2}>
                        {user?.display_name}
                      </Text>
                      <Text size="xs" c="dimmed" lh={1.2}>
                        {roleLabel(user?.org_role)}
                      </Text>
                    </Box>
                  </Group>
                </UnstyledButton>
              </Menu.Target>
              <Menu.Dropdown>
                <Menu.Label>
                  @{user?.username} · clearance {user?.clearance}
                </Menu.Label>
                <Menu.Item disabled>
                  <Text size="xs">Role decides what you can do; clearance decides which cases you can see.</Text>
                </Menu.Item>
                <Menu.Item leftSection={<IconUserCircle size={16} />} onClick={() => navigate('/kh/profile')}>
                  My profile
                </Menu.Item>
                <Menu.Item leftSection={<IconShieldLock size={16} />} onClick={() => navigate('/kh/account')}>
                  Account and two-step verification
                </Menu.Item>
                <Menu.Divider />
                <Menu.Item
                  leftSection={<IconLogout size={16} />}
                  onClick={() => {
                    logout()
                    navigate('/login')
                  }}
                >
                  Log out
                </Menu.Item>
              </Menu.Dropdown>
            </Menu>
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Navbar p="xs" className="no-print">
        <AppShell.Section grow component={ScrollArea}>
          {user && CREATORS.includes(user.org_role) && (
            <NavLink
              component={Link}
              to="/kh/cases/new"
              label="Register a case"
              leftSection={<IconPlus size={16} />}
              onClick={close}
              variant="filled"
              active
              mb="sm"
              styles={{ root: { borderRadius: 4 }, label: { fontWeight: 600, fontSize: 13 } }}
            />
          )}
          <Section title="Investigation" items={investigation} onNavigate={close} />
          {isAdmin && <Section title="Administration" items={administration} onNavigate={close} />}
          <Section title="Case Intelligence" items={intelligence} onNavigate={close} />
        </AppShell.Section>
        <AppShell.Section>
          <Divider mb={6} />
          <Text size="10px" c="dimmed" px="sm" pb={4}>
            Nothing is ever deleted: every change is a permanent, attributed record.
          </Text>
        </AppShell.Section>
      </AppShell.Navbar>

      <AppShell.Main>
        <Container size={inKnightHawk ? 1360 : 'lg'} pb="xl" px={0}>
          <Suspense fallback={<Center py="xl"><Loader size="sm" /></Center>}>
            <Outlet />
          </Suspense>
          {!inKnightHawk && (
            <Text size="xs" c="dimmed" mt="xl" ta="center">
              Historical cases: Indian Supreme Court Judgments dataset (Dattam Labs), CC-BY-4.0. Similarity scores
              indicate relevance for review, not legal equivalence.
            </Text>
          )}
        </Container>
      </AppShell.Main>
    </AppShell>
  )
}
