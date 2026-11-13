// Your account: two-step verification (TOTP, phase CM-7). Scan the QR code with an authenticator app, confirm one code,
// and every later login asks for a code too. Platform administrators and supervisors may be required to use it.

import { Alert, Badge, Button, Code, Group, Image, Modal, Paper, PinInput, Stack, Text } from '@mantine/core'
import { IconKey, IconShieldCheck, IconShieldLock } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { apiFetch } from '../../api/client'
import { useAuth } from '../../auth/useAuth'
import { toastDone, toastError } from '../feedback'
import { roleLabel } from '../labels'
import type { MfaSetup, MfaStatus } from '../types'
import { Loaded, PageHeader } from '../ui'
import { ChangePasswordForm } from './ChangePasswordForm'
import { formatWhen } from '../time'

const mfaApi = {
  status: () => apiFetch<MfaStatus>('/auth/mfa'),
  setup: () => apiFetch<MfaSetup>('/auth/mfa/setup', { method: 'POST' }),
  confirm: (code: string) => apiFetch<MfaStatus>('/auth/mfa/confirm', { method: 'POST', json: { code } }),
  disable: (code: string) => apiFetch<MfaStatus>('/auth/mfa/disable', { method: 'POST', json: { code } }),
}

export function AccountPage() {
  const { user } = useAuth()
  const client = useQueryClient()
  const status = useQuery({ queryKey: ['auth', 'mfa'], queryFn: mfaApi.status })
  const [setup, setSetup] = useState<MfaSetup | null>(null)
  const [turningOff, setTurningOff] = useState(false)
  const start = useMutation({ mutationFn: mfaApi.setup, onSuccess: setSetup, onError: (error) => toastError(error, 'Not started') })
  const refresh = () => client.invalidateQueries({ queryKey: ['auth', 'mfa'] })
  return (
    <Stack gap="md" maw={760}>
      <PageHeader eyebrow="Account" title={user?.display_name ?? 'Your account'}>
        <Text size="sm" c="dimmed">
          @{user?.username} · {roleLabel(user?.org_role)} · clearance {user?.clearance}
        </Text>
      </PageHeader>
      <Paper withBorder p="md" radius="md">
        <Loaded query={status}>
          {(s) => (
            <Stack gap="sm">
              <Group justify="space-between">
                <Group gap="xs">
                  <IconShieldLock size={20} />
                  <Text fw={600}>Two-step verification</Text>
                  <Badge color={s.enabled ? 'teal' : 'gray'} variant="light">
                    {s.enabled ? 'on' : 'off'}
                  </Badge>
                  {s.required && (
                    <Badge color="orange" variant="light">
                      required for your role
                    </Badge>
                  )}
                </Group>
                {s.enabled ? (
                  <Button variant="default" size="xs" onClick={() => setTurningOff(true)}>
                    Turn off
                  </Button>
                ) : (
                  <Button size="xs" leftSection={<IconShieldCheck size={14} />} loading={start.isPending} onClick={() => start.mutate()}>
                    Turn on
                  </Button>
                )}
              </Group>
              <Text size="sm" c="dimmed">
                After your password, Knight Hawk asks for a 6-digit code from an authenticator app on your phone (any app that supports TOTP). Someone
                who learns your password still can't log in.
              </Text>
              {s.enabled && (
                <Text size="sm">
                  On since {formatWhen(s.confirmed_at)}. {s.verified_now ? 'This login used a code.' : 'This login did not use a code: log in again to use one.'}
                </Text>
              )}
              {s.required && !s.verified_now && (
                <Alert color="orange" variant="light" p="xs">
                  Your organisation requires two-step verification for privileged actions (sealing, hand-overs, legal holds,
                  retention decisions). {s.enabled ? 'Log out and in again with a code.' : 'Turn it on, then log in again with a code.'}
                </Alert>
              )}
            </Stack>
          )}
        </Loaded>
      </Paper>
      <Paper withBorder p="md" radius="md">
        <Stack gap="sm">
          <Group gap="xs">
            <IconKey size={20} />
            <Text fw={600}>Password</Text>
          </Group>
          <ChangePasswordForm />
        </Stack>
      </Paper>
      {setup && (
        <SetupDialog
          setup={setup}
          onClose={() => setSetup(null)}
          onDone={() => {
            setSetup(null)
            refresh()
            toastDone('Two-step verification is on: your next login asks for a code')
          }}
        />
      )}
      {turningOff && (
        <CodeDialog
          title="Turn off two-step verification"
          action="Turn off"
          onClose={() => setTurningOff(false)}
          submit={(code) => mfaApi.disable(code)}
          onDone={() => {
            setTurningOff(false)
            refresh()
            toastDone('Two-step verification is off')
          }}
        />
      )}
    </Stack>
  )
}

function SetupDialog({ setup, onClose, onDone }: { setup: MfaSetup; onClose: () => void; onDone: () => void }) {
  const [code, setCode] = useState('')
  const confirm = useMutation({ mutationFn: () => mfaApi.confirm(code), onSuccess: onDone, onError: (error) => toastError(error, 'Not turned on') })
  return (
    <Modal opened onClose={onClose} title={<Text fw={600}>Turn on two-step verification</Text>} size="md">
      <Stack gap="sm">
        <Text size="sm">1. In your authenticator app, add an account by scanning this code.</Text>
        <Image src={setup.qr_svg} alt="QR code for the authenticator app" w={220} h={220} mx="auto" radius="sm" bg="white" />
        <Text size="xs" c="dimmed">
          Can't scan it? Type this key instead: <Code>{setup.secret}</Code>
        </Text>
        <Text size="sm">2. Enter the 6-digit code the app shows now.</Text>
        <PinInput length={6} type="number" oneTimeCode value={code} onChange={setCode} aria-label="Verification code" mx="auto" />
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={code.length !== 6} loading={confirm.isPending} onClick={() => confirm.mutate()}>
            Turn on
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}

function CodeDialog({ title, action, onClose, submit, onDone }: { title: string; action: string; onClose: () => void; submit: (code: string) => Promise<unknown>; onDone: () => void }) {
  const [code, setCode] = useState('')
  const run = useMutation({ mutationFn: () => submit(code), onSuccess: onDone, onError: (error) => toastError(error) })
  return (
    <Modal opened onClose={onClose} title={<Text fw={600}>{title}</Text>} size="sm">
      <Stack gap="sm">
        <Text size="sm">Enter the code your authenticator app shows now.</Text>
        <PinInput length={6} type="number" oneTimeCode value={code} onChange={setCode} aria-label="Verification code" />
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button color="red" disabled={code.length !== 6} loading={run.isPending} onClick={() => run.mutate()}>
            {action}
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}
