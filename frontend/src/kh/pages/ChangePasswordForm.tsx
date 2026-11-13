// Choosing your own password. Used on the Account page, and (alone on the screen) after a login with a temporary password:
// the person who made the account, or reset the password, handed it over once; nobody but its owner should know the real one.

import { Alert, Button, Center, Group, Paper, PasswordInput, Stack, Text, Title } from '@mantine/core'
import { IconKey, IconLogout } from '@tabler/icons-react'
import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { apiFetch } from '../../api/client'
import { useAuth } from '../../auth/useAuth'
import { toastDone, toastError } from '../feedback'

const MIN = 12

export function ChangePasswordForm({ forced = false }: { forced?: boolean }) {
  const { reload } = useAuth()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [again, setAgain] = useState('')
  const mutation = useMutation({
    mutationFn: () => apiFetch<void>('/auth/change-password', { method: 'POST', json: { current_password: current, new_password: next } }),
    onSuccess: async () => {
      toastDone('Your password was changed')
      setCurrent('')
      setNext('')
      setAgain('')
      await reload()
    },
    onError: (error) => toastError(error, 'The password was not changed'),
  })
  const tooShort = next.length > 0 && next.length < MIN
  const mismatch = again.length > 0 && again !== next
  const ready = current.length > 0 && next.length >= MIN && next === again && next !== current
  return (
    <Stack gap="sm">
      <PasswordInput label={forced ? 'The temporary password you were given' : 'Your current password'} value={current} onChange={(e) => setCurrent(e.currentTarget.value)} autoComplete="current-password" required />
      <PasswordInput
        label="Your new password"
        description={`At least ${MIN} characters. A few unrelated words make a good one.`}
        value={next}
        onChange={(e) => setNext(e.currentTarget.value)}
        error={tooShort ? `At least ${MIN} characters` : undefined}
        autoComplete="new-password"
        required
      />
      <PasswordInput label="Repeat the new password" value={again} onChange={(e) => setAgain(e.currentTarget.value)} error={mismatch ? 'The two do not match' : undefined} autoComplete="new-password" required />
      <Group justify="flex-end">
        <Button leftSection={<IconKey size={16} />} disabled={!ready} loading={mutation.isPending} onClick={() => mutation.mutate()}>
          Change password
        </Button>
      </Group>
    </Stack>
  )
}

/** Shown instead of the whole application while a temporary password is in use. */
export function PasswordChangeRequired() {
  const { user, logout } = useAuth()
  return (
    <Center mih="100vh" p="md">
      <Paper withBorder radius="md" p="xl" maw={460} w="100%">
        <Stack gap="md">
          <div>
            <Title order={2} size="h3">
              Choose your own password
            </Title>
            <Text size="sm" c="dimmed">
              {user?.display_name}, you are signed in with a temporary password that someone handed to you. Choose a password only you know. Until you do, nothing else is available.
            </Text>
          </div>
          <Alert color="gray" variant="light">
            Your new password is never shown to anyone, not even to the person who created your account.
          </Alert>
          <ChangePasswordForm forced />
          <Button variant="subtle" color="gray" size="xs" leftSection={<IconLogout size={14} />} onClick={logout}>
            Sign out instead
          </Button>
        </Stack>
      </Paper>
    </Center>
  )
}
