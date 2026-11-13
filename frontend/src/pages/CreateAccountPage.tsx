// An officer creates their own login (docs/case-management/13-plain-case-design.md, section 12). It works only for an officer who is in the
// register, with the name written there; the new login starts with view-only access and a Supervisor or Administrator raises it.

import { Alert, Anchor, Button, Center, Group, Paper, PasswordInput, Stack, Text, TextInput, ThemeIcon, Title } from '@mantine/core'
import { IconAlertTriangle, IconCircleCheck } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { Link, Navigate } from 'react-router'
import { registerYourself, registrationStatus } from '../api/endpoints'
import type { RegisteredOut } from '../api/types'
import { useAuth } from '../auth/useAuth'
import { HawkMark } from '../kh/Brand'
import { AUTH_BACKGROUND } from './authBackground'

const MIN_PASSWORD = 12

export function CreateAccountPage() {
  const { user } = useAuth()
  const status = useQuery({ queryKey: ['auth', 'registration'], queryFn: registrationStatus, staleTime: 60_000 })
  const [officerNumber, setOfficerNumber] = useState('')
  const [fullName, setFullName] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [again, setAgain] = useState('')
  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [done, setDone] = useState<RegisteredOut | null>(null)

  if (user) return <Navigate to="/kh" replace />

  const mismatch = again !== '' && again !== password
  const emailBad = email.trim() !== '' && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email.trim())
  const phoneBad = phone.trim() !== '' && !/^[0-9+()\-. ]{6,40}$/.test(phone.trim())
  const ready = officerNumber.trim().length >= 2 && fullName.trim().length >= 3 && username.trim().length >= 3 && password.length >= MIN_PASSWORD && again === password && !emailBad && !phoneBad

  async function submit(event: FormEvent) {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      setDone(
        await registerYourself({ officer_number: officerNumber.trim(), full_name: fullName.trim(), username: username.trim(), password, email: email.trim() || null, phone: phone.trim() || null }),
      )
      setPassword('')
      setAgain('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'The login was not created')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Center mih="100vh" p="md" style={{ background: AUTH_BACKGROUND }}>
      <Paper withBorder radius="md" w={520} maw="100%" p="xl">
        <Stack>
          <Group gap="xs">
            <HawkMark size={28} />
            <Text fw={800} style={{ letterSpacing: 1.5 }}>
              KNIGHT HAWK
            </Text>
          </Group>
          {done ? (
            <Stack gap="md">
              <Group gap="sm" wrap="nowrap" align="flex-start">
                <ThemeIcon color="green" variant="light" size={36} radius="xl">
                  <IconCircleCheck size={22} />
                </ThemeIcon>
                <div>
                  <Title order={1} size="h3">
                    Your login is ready
                  </Title>
                  <Text size="sm" c="dimmed">
                    {done.display_name} · {done.station}
                  </Text>
                </div>
              </Group>
              <Text size="sm">{done.message}</Text>
              <Button component={Link} to="/login" fullWidth>
                Log in as {done.username}
              </Button>
            </Stack>
          ) : status.data && !status.data.enabled ? (
            <Stack gap="sm">
              <Title order={1} size="h3">
                Creating your own login is switched off
              </Title>
              <Text size="sm" c="dimmed">
                Ask your Supervisor or Administrator to make your login.
              </Text>
              <Anchor component={Link} to="/login" size="sm">
                Back to the log in page
              </Anchor>
            </Stack>
          ) : (
            <form onSubmit={submit}>
              <Stack>
                <div>
                  <Title order={1} size="h3">
                    Create your login
                  </Title>
                  <Text c="dimmed" size="sm">
                    For officers in the officer register. Your login starts with view-only access; your Supervisor or Administrator can give you more.
                  </Text>
                </div>
                <TextInput label="Officer ID" value={officerNumber} onChange={(e) => setOfficerNumber(e.currentTarget.value)} required autoFocus maxLength={32} />
                <TextInput label="Full name (as in the register)" value={fullName} onChange={(e) => setFullName(e.currentTarget.value)} required maxLength={200} />
                <TextInput label="Username" autoComplete="username" value={username} onChange={(e) => setUsername(e.currentTarget.value)} required maxLength={64} />
                <PasswordInput label="Password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.currentTarget.value)} required minLength={MIN_PASSWORD} />
                <PasswordInput
                  label="Repeat the password"
                  autoComplete="new-password"
                  value={again}
                  onChange={(e) => setAgain(e.currentTarget.value)}
                  required
                  error={mismatch ? 'The two passwords are not the same' : undefined}
                />
                <TextInput label="Email (optional)" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.currentTarget.value)} maxLength={200} error={emailBad ? 'Not a valid email address' : undefined} />
                <TextInput label="Phone (optional)" type="tel" autoComplete="tel" value={phone} onChange={(e) => setPhone(e.currentTarget.value)} maxLength={40} error={phoneBad ? 'Use digits, spaces and + ( ) - . only' : undefined} />
                {error && (
                  <Alert color="red" icon={<IconAlertTriangle size={18} />}>
                    {error}
                  </Alert>
                )}
                <Button type="submit" loading={submitting} disabled={!ready} fullWidth>
                  Create my login
                </Button>
                <Anchor component={Link} to="/login" size="sm" ta="center">
                  I already have a login
                </Anchor>
              </Stack>
            </form>
          )}
        </Stack>
      </Paper>
    </Center>
  )
}
