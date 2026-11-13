// Building blocks shared by the Knight Hawk screens.

import {
  ActionIcon,
  Alert,
  Anchor,
  Badge,
  Box,
  Button,
  Center,
  CopyButton,
  Group,
  Loader,
  Modal,
  Paper,
  SimpleGrid,
  Stack,
  Text,
  Textarea,
  ThemeIcon,
  Title,
  Tooltip,
} from '@mantine/core'
import { IconAlertTriangle, IconCheck, IconCopy, IconInbox, IconShieldCheck, IconShieldX } from '@tabler/icons-react'
import type { UseQueryResult } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'
import { Link } from 'react-router'
import { ApiError } from '../api/client'
import { errorText } from './feedback'
import { formatWhen, timeAgo } from './time'
import { UserAvatar } from '../components/UserAvatar'
import { classificationLook, entryLook, integrityLook, priorityLook, workflowLook } from './labels'
import type { Person } from './types'

// ------------------------------------------------------------------ status labels

function Look({ look, size = 'sm' }: { look: { label: string; color: string }; size?: string }) {
  return (
    <Badge color={look.color} size={size} style={{ flexShrink: 0 }}>
      {look.label}
    </Badge>
  )
}
export const WorkflowBadge = ({ value }: { value?: string | null }) => <Look look={workflowLook(value)} />
export const PriorityBadge = ({ value }: { value?: string | null }) => <Look look={priorityLook(value)} />
export const ClassificationBadge = ({ value }: { value?: string | null }) => <Look look={classificationLook(value)} />
export const EntryBadge = ({ value }: { value?: string | null }) => <Look look={entryLook(value)} size="xs" />

export function IntegrityBadge({ result }: { result?: string | null }) {
  const look = integrityLook(result)
  const icon = result === 'match' ? <IconShieldCheck size={12} /> : <IconShieldX size={12} />
  return (
    <Badge color={look.color} size="sm" leftSection={icon} style={{ flexShrink: 0 }}>
      {look.label}
    </Badge>
  )
}

// ------------------------------------------------------------------ identifiers

/** A history entry as "Entry 14", linking to the case's history. Never a code. */
export function EntryNumber({ seq, caseId }: { seq?: number | null; caseId?: string }) {
  if (seq === null || seq === undefined) return <Text span c="dimmed" size="sm">—</Text>
  const text = (
    <Text span fz="xs" fw={600} c="hawk.3" style={{ whiteSpace: 'nowrap' }}>
      Entry {seq}
    </Text>
  )
  return caseId ? (
    <Anchor component={Link} to={`/kh/case/${caseId}/history#entry-${seq}`} underline="never" aria-label={`Entry ${seq}`}>
      {text}
    </Anchor>
  ) : (
    text
  )
}

export function Copy({ value }: { value: string }) {
  return (
    <CopyButton value={value} timeout={1500}>
      {({ copied, copy }) => (
        <Tooltip label={copied ? 'Copied' : 'Copy'}>
          <ActionIcon size="xs" variant="subtle" color={copied ? 'teal' : 'gray'} onClick={copy} aria-label="Copy">
            {copied ? <IconCheck size={12} /> : <IconCopy size={12} />}
          </ActionIcon>
        </Tooltip>
      )}
    </CopyButton>
  )
}

export function PersonName({ person, size = 'sm' }: { person?: Person | null; size?: 'xs' | 'sm' }) {
  if (!person) return <Text span c="dimmed" size={size}>—</Text>
  return (
    <Group gap={6} wrap="nowrap" component="span" style={{ display: 'inline-flex' }}>
      <UserAvatar id={person.id} name={person.display_name} version={person.photo} size={size === 'xs' ? 18 : 22} />
      <Tooltip label={`@${person.username}`} openDelay={500}>
        <Text span size={size} style={{ whiteSpace: 'nowrap' }}>
          {person.display_name}
        </Text>
      </Tooltip>
    </Group>
  )
}

// ------------------------------------------------------------------ time


export function When({ at, size = 'sm' }: { at?: string | null; size?: 'xs' | 'sm' }) {
  if (!at) return <Text span c="dimmed" size={size}>—</Text>
  return (
    <Tooltip label={formatWhen(at)} openDelay={300}>
      <Text span size={size} c="dimmed" style={{ whiteSpace: 'nowrap' }}>
        {timeAgo(at)}
      </Text>
    </Tooltip>
  )
}

// ------------------------------------------------------------------ page structure

export function PageHeader({ title, eyebrow, children, actions }: { title: ReactNode; eyebrow?: ReactNode; children?: ReactNode; actions?: ReactNode }) {
  return (
    <Group justify="space-between" align="flex-start" mb="md" wrap="wrap" gap="sm">
      <Stack gap={4} style={{ minWidth: 0 }}>
        {eyebrow && (
          <Text size="xs" tt="uppercase" fw={600} c="dimmed" style={{ letterSpacing: 0.6 }}>
            {eyebrow}
          </Text>
        )}
        <Title order={2} size="h3">
          {title}
        </Title>
        {children}
      </Stack>
      {actions && <Group gap="xs">{actions}</Group>}
    </Group>
  )
}

export function Panel({ title, actions, children, p = 'md' }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; p?: string }) {
  return (
    <Paper withBorder radius="sm" p={p}>
      {(title || actions) && (
        // A panel without padding holds a full-width table: its title keeps its own spacing.
        <Group justify="space-between" mb="sm" gap="xs" px={p === '0' ? 'md' : undefined} pt={p === '0' ? 'sm' : undefined}>
          {typeof title === 'string' ? (
            <Text fw={600} size="sm">
              {title}
            </Text>
          ) : (
            title
          )}
          {actions}
        </Group>
      )}
      {children}
    </Paper>
  )
}

export function Stat({ label, value, hint, color }: { label: string; value: ReactNode; hint?: ReactNode; color?: string }) {
  return (
    <Paper withBorder radius="sm" p="sm">
      <Text size="xs" c="dimmed" tt="uppercase" fw={600} style={{ letterSpacing: 0.5 }}>
        {label}
      </Text>
      <Text fw={700} fz={26} lh={1.25} c={color}>
        {value}
      </Text>
      {hint && (
        <Text size="xs" c="dimmed">
          {hint}
        </Text>
      )}
    </Paper>
  )
}

export function Facts({ items, cols = 2 }: { items: [string, ReactNode][]; cols?: number }) {
  return (
    <SimpleGrid cols={{ base: 1, sm: cols }} spacing="xs" verticalSpacing={6}>
      {items.map(([label, value]) => (
        <Box key={label}>
          <Text size="xs" c="dimmed">
            {label}
          </Text>
          <Box fz="sm">{value === null || value === undefined || value === '' ? <Text span c="dimmed" size="sm">—</Text> : value}</Box>
        </Box>
      ))}
    </SimpleGrid>
  )
}

export function EmptyState({ title, children, icon }: { title: string; children?: ReactNode; icon?: ReactNode }) {
  return (
    <Center py="xl">
      <Stack align="center" gap={6} maw={420}>
        <ThemeIcon variant="light" color="gray" size={40} radius="xl">
          {icon ?? <IconInbox size={22} />}
        </ThemeIcon>
        <Text fw={600} size="sm">
          {title}
        </Text>
        {children && (
          <Text size="sm" c="dimmed" ta="center">
            {children}
          </Text>
        )}
      </Stack>
    </Center>
  )
}


export function Failure({ error, title = 'Could not load' }: { error: unknown; title?: string }) {
  const notFound = error instanceof ApiError && error.status === 404
  return (
    <Alert color={notFound ? 'gray' : 'red'} icon={<IconAlertTriangle size={18} />} title={notFound ? 'Not found' : title}>
      {notFound ? "It doesn't exist, or you don't have access to it." : errorText(error)}
    </Alert>
  )
}

/** Loading, error, or the content for a loaded query. */
export function Loaded<T>({ query, children }: { query: UseQueryResult<T>; children: (data: T) => ReactNode }) {
  if (query.isPending) {
    return (
      <Center py="xl">
        <Loader size="sm" />
      </Center>
    )
  }
  if (query.isError) return <Failure error={query.error} />
  return <>{children(query.data)}</>
}

// ------------------------------------------------------------------ feedback and confirmation


/**
 * Confirmation for sensitive operations (spec §21: modal confirmations), with a reason when one is needed.
 * Nothing in Knight Hawk is deleted: the dialog says what happens instead.
 */
export function ConfirmModal({
  opened,
  onClose,
  title,
  children,
  confirmLabel,
  color = 'hawk',
  reason = 'none',
  reasonLabel = 'Reason (kept in the history)',
  minReason = 5,
  onConfirm,
  loading,
}: {
  opened: boolean
  onClose: () => void
  title: string
  children?: ReactNode
  confirmLabel: string
  color?: string
  reason?: 'none' | 'optional' | 'required'
  reasonLabel?: string
  minReason?: number
  onConfirm: (reason: string) => void
  loading?: boolean
}) {
  const [text, setText] = useState('')
  const missing = reason === 'required' && text.trim().length < minReason
  return (
    <Modal
      opened={opened}
      onClose={() => {
        setText('')
        onClose()
      }}
      title={<Text fw={600}>{title}</Text>}
      size="md"
    >
      <Stack gap="sm">
        {children}
        {reason !== 'none' && (
          <Textarea
            label={reasonLabel}
            description={reason === 'required' ? `At least ${minReason} characters.` : 'Optional.'}
            value={text}
            onChange={(e) => setText(e.currentTarget.value)}
            autosize
            minRows={2}
            maxRows={6}
            maxLength={2000}
            data-autofocus
          />
        )}
        <Group justify="flex-end" gap="xs">
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button color={color} disabled={missing} loading={loading} onClick={() => onConfirm(text.trim())}>
            {confirmLabel}
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}

/** A short line telling where something came from (provenance). */
export function Provenance({ children }: { children: ReactNode }) {
  return (
    <Text size="xs" c="dimmed" fs="italic">
      {children}
    </Text>
  )
}
