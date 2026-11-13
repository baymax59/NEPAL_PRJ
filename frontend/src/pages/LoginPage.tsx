import { Alert, Anchor, Box, Button, Center, Group, Paper, PasswordInput, PinInput, SimpleGrid, Stack, Text, TextInput, ThemeIcon, Title } from '@mantine/core'
import { IconAlertTriangle, IconFingerprint, IconHistory, IconLock } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { useState, type FormEvent, type ReactNode } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router'
import { registrationStatus } from '../api/endpoints'
import { useAuth } from '../auth/useAuth'
import { HawkMark } from '../kh/Brand'
import { AUTH_BACKGROUND } from './authBackground'

function Principle({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <Group gap="sm" wrap="nowrap" align="flex-start">
      <ThemeIcon variant="light" color="hawk" size={32} radius="sm">
        {icon}
      </ThemeIcon>
      <div>
        <Text size="sm" fw={600}>
          {title}
        </Text>
        <Text size="xs" c="dimmed">
          {children}
        </Text>
      </div>
    </Group>
  )
}

export function LoginPage() {
  const { user, login, loginSecondStep } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const from = (location.state as { from?: string } | null)?.from ?? '/kh'
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [ticket, setTicket] = useState<string | null>(null)
  const [code, setCode] = useState('')
  const signup = useQuery({ queryKey: ['auth', 'registration'], queryFn: registrationStatus, staleTime: 60_000, retry: false })

  if (user) return <Navigate to={from} replace />

  async function submit(event: FormEvent) {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      if (ticket) {
        await loginSecondStep(ticket, code)
        navigate(from, { replace: true })
      } else {
        const next = await login(username, password)
        if (next) {
          setTicket(next.mfaTicket) // the password was right: now the code
          setPassword('')
        } else {
          navigate(from, { replace: true })
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Center mih="100vh" p="md" style={{ background: AUTH_BACKGROUND }}>
      <Paper withBorder radius="md" w={880} maw="100%" style={{ overflow: 'hidden' }}>
        <SimpleGrid cols={{ base: 1, sm: 2 }} spacing={0}>
          <Box p="xl" bg="var(--mantine-color-default-hover)" visibleFrom="sm">
            <Stack gap="lg" h="100%" justify="space-between">
              <Stack gap="xs">
                <Group gap="sm">
                  <HawkMark size={40} />
                  <div>
                    <Text fw={800} size="lg" style={{ letterSpacing: 2 }}>
                      KNIGHT HAWK
                    </Text>
                    <Text size="xs" c="dimmed">
                      Case Management and Case Intelligence
                    </Text>
                  </div>
                </Group>
                <Text size="sm" c="dimmed" mt="sm">
                  Every case is a permanent record: its folders, the notes and exhibits added to it, and a numbered history that can be checked at any time.
                </Text>
              </Stack>
              <Stack gap="md">
                <Principle icon={<IconLock size={18} />} title="Nothing is deleted">
                  Corrections are new versions; earlier work stays, attributed.
                </Principle>
                <Principle icon={<IconHistory size={18} />} title="History is never rewritten">
                  Every change is a numbered entry, in order, and the whole history can be checked.
                </Principle>
                <Principle icon={<IconFingerprint size={18} />} title="Evidence is never overwritten">
                  Each exhibit is stored once and checked automatically, with its chain of custody.
                </Principle>
              </Stack>
            </Stack>
          </Box>
          <Box p="xl">
            <form onSubmit={submit}>
              <Stack>
                <div>
                  <Group gap="xs" hiddenFrom="sm" mb="xs">
                    <HawkMark size={28} />
                    <Text fw={800} style={{ letterSpacing: 1.5 }}>
                      KNIGHT HAWK
                    </Text>
                  </Group>
                  <Title order={1} size="h3">
                    Log in
                  </Title>
                  <Text c="dimmed" size="sm">
                    Use your own login, or the one your Supervisor or Administrator gave you.
                  </Text>
                </div>
                {ticket ? (
                  <Stack gap={6}>
                    <Text size="sm" fw={600}>
                      Two-step verification
                    </Text>
                    <Text size="sm" c="dimmed">
                      Enter the 6-digit code shown in your authenticator app for Knight Hawk.
                    </Text>
                    <PinInput length={6} type="number" oneTimeCode value={code} onChange={setCode} aria-label="Verification code" autoFocus />
                    <Anchor
                      component="button"
                      type="button"
                      size="xs"
                      onClick={() => {
                        setTicket(null)
                        setCode('')
                        setError(null)
                      }}
                    >
                      Start again with another account
                    </Anchor>
                  </Stack>
                ) : (
                  <>
                    <TextInput label="Username" autoComplete="username" value={username} onChange={(e) => setUsername(e.currentTarget.value)} required autoFocus />
                    <PasswordInput label="Password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.currentTarget.value)} required />
                  </>
                )}
                {error && (
                  <Alert color="red" icon={<IconAlertTriangle size={18} />}>
                    {error}
                  </Alert>
                )}
                <Button type="submit" loading={submitting} fullWidth disabled={ticket !== null && code.length !== 6}>
                  {ticket ? 'Verify and log in' : 'Log in'}
                </Button>
                {signup.data?.enabled && !ticket && (
                  <Text size="sm" ta="center">
                    No login yet?{' '}
                    <Anchor component={Link} to="/create-account">
                      Create your own login
                    </Anchor>
                  </Text>
                )}
                <Text size="xs" c="dimmed">
                  For authorised use only. Logins, case views and every change are recorded in an audit log.
                </Text>
              </Stack>
            </form>
          </Box>
        </SimpleGrid>
      </Paper>
    </Center>
  )
}
