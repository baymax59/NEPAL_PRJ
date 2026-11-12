// Small building blocks shared by the pages.

import { Alert, Badge, Group, Paper, Progress, Stack, Text, Title, Tooltip } from '@mantine/core'
import { IconAlertTriangle, IconInfoCircle } from '@tabler/icons-react'
import type { ReactNode } from 'react'
import { ApiError } from '../api/client'
import { NOT_IN_SOURCE } from '../lib/format'

/** The value, or a clearly marked "not available in source". */
export function Value({ children }: { children: ReactNode }) {
  if (children === null || children === undefined || children === '') {
    return (
      <Text size="sm" c="dimmed" fs="italic" component="span">
        {NOT_IN_SOURCE}
      </Text>
    )
  }
  return (
    <Text size="sm" component="span">
      {children}
    </Text>
  )
}

/** A stat tile: label above, number below (KPI row on the search page). */
export function StatTile({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <Paper withBorder p="md" radius="md">
      <Text size="sm" c="dimmed">
        {label}
      </Text>
      <Text component="div" fw={600} fz={28} lh={1.2}>
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

/** Relevance 0-100 as a number and a single-colour meter. It orders results; it is not a probability. */
export function RelevanceMeter({ value, note }: { value: number; note: string }) {
  return (
    <Tooltip label={note} multiline w={320} withArrow>
      <Stack gap={4} w={120} style={{ cursor: 'help' }} aria-label={`Relevance ${value} out of 100`}>
        <Group justify="space-between" gap={4}>
          <Text size="xs" c="dimmed">
            Relevance
          </Text>
          <Text size="sm" fw={600}>
            {value}
          </Text>
        </Group>
        <Progress value={value} size="sm" aria-hidden />
      </Stack>
    </Tooltip>
  )
}

const MATCH_LABELS: Record<string, string> = {
  'keyword+semantic': 'Words + meaning',
  keyword: 'Words',
  semantic: 'Meaning',
  'text+provisions': 'Text + provisions',
  text: 'Text',
  provisions: 'Provisions',
}

export function MatchBadge({ type }: { type: string }) {
  return (
    <Badge variant="light" color="gray" size="sm">
      Matched by: {MATCH_LABELS[type] ?? type}
    </Badge>
  )
}

/** A titled block of the details page. */
export function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <Paper withBorder p="lg" radius="md" id={id}>
      <Title order={3} size="h4" mb="sm">
        {title}
      </Title>
      {children}
    </Paper>
  )
}

export function ErrorAlert({ error, title = 'Could not load' }: { error: unknown; title?: string }) {
  const message = error instanceof ApiError || error instanceof Error ? error.message : 'Something went wrong.'
  return (
    <Alert color="red" icon={<IconAlertTriangle size={18} />} title={title}>
      {message}
    </Alert>
  )
}

export function Notices({ notices }: { notices: string[] }) {
  return notices.map((notice) => (
    <Alert key={notice} color="yellow" icon={<IconAlertTriangle size={18} />}>
      {notice}
    </Alert>
  ))
}

export function RelevanceNote({ note }: { note: string }) {
  return (
    <Alert color="blue" variant="light" icon={<IconInfoCircle size={18} />}>
      <Text size="sm">{note}</Text>
    </Alert>
  )
}
