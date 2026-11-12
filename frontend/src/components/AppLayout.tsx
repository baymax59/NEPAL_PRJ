import {
  ActionIcon,
  AppShell,
  Badge,
  Button,
  Container,
  Group,
  Text,
  Tooltip,
  useComputedColorScheme,
  useMantineColorScheme,
} from '@mantine/core'
import { IconFileUpload, IconListSearch, IconLogout, IconMoon, IconShieldCheck, IconSun } from '@tabler/icons-react'
import type { ReactNode } from 'react'
import { Link, Outlet, useLocation, useNavigate } from 'react-router'
import { useAuth } from '../auth/useAuth'

function NavButton({ to, icon, children }: { to: string; icon: ReactNode; children: ReactNode }) {
  const { pathname } = useLocation()
  const active = to === '/' ? pathname === '/' || pathname.startsWith('/cases') : pathname.startsWith(to)
  return (
    <Button component={Link} to={to} variant={active ? 'light' : 'subtle'} size="sm" leftSection={icon}>
      {children}
    </Button>
  )
}

export function AppLayout() {
  const { user, logout, hasRole } = useAuth()
  const navigate = useNavigate()
  const { setColorScheme } = useMantineColorScheme()
  const scheme = useComputedColorScheme('light')

  return (
    <AppShell header={{ height: 60 }} padding="md">
      <AppShell.Header>
        <Container size="lg" h="100%">
          <Group h="100%" justify="space-between" wrap="nowrap">
            <Group gap="xs" wrap="nowrap">
              <Text component={Link} to="/" fw={700} mr="md" style={{ textDecoration: 'none', color: 'inherit' }}>
                Similar Case Search
              </Text>
              <NavButton to="/" icon={<IconListSearch size={16} />}>
                Search
              </NavButton>
              {hasRole('analyst', 'admin') && (
                <NavButton to="/new" icon={<IconFileUpload size={16} />}>
                  New case
                </NavButton>
              )}
              {hasRole('admin') && (
                <NavButton to="/audit" icon={<IconShieldCheck size={16} />}>
                  Audit log
                </NavButton>
              )}
            </Group>
            <Group gap="sm" wrap="nowrap">
              <Text size="sm" visibleFrom="sm">
                {user?.display_name}
              </Text>
              <Tooltip label="Role decides what you can do; clearance decides which cases you can see.">
                <Badge variant="light" color="gray" visibleFrom="sm">
                  {user?.role} · clearance {user?.clearance}
                </Badge>
              </Tooltip>
              <ActionIcon
                variant="subtle"
                onClick={() => setColorScheme(scheme === 'dark' ? 'light' : 'dark')}
                aria-label={scheme === 'dark' ? 'Use light mode' : 'Use dark mode'}
              >
                {scheme === 'dark' ? <IconSun size={18} /> : <IconMoon size={18} />}
              </ActionIcon>
              <Button
                variant="subtle"
                size="sm"
                leftSection={<IconLogout size={16} />}
                onClick={() => {
                  logout()
                  navigate('/login')
                }}
              >
                Log out
              </Button>
            </Group>
          </Group>
        </Container>
      </AppShell.Header>
      <AppShell.Main>
        <Container size="lg" pb="xl">
          <Outlet />
          <Text size="xs" c="dimmed" mt="xl" ta="center">
            Historical cases: Indian Supreme Court Judgments dataset (Dattam Labs), CC-BY-4.0. Similarity scores
            indicate relevance for review, not legal equivalence.
          </Text>
        </Container>
      </AppShell.Main>
    </AppShell>
  )
}
