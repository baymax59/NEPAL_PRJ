// Shared pieces of the Case Intelligence tab: links to the exhibit or note a result came from, notices, the
// "what has been read" bar, and the relevance meter.

import { Alert, Anchor, Badge, Button, Group, List, Paper, Progress, Stack, Text, Tooltip } from '@mantine/core'
import { IconAlertTriangle, IconBook2, IconInfoCircle, IconRefresh } from '@tabler/icons-react'
import { Link } from 'react-router'
import type { Coverage } from '../../types'
import { sourceHref, type SourceLike } from './format'

export function SourceLink({ caseId, source, pages }: { caseId: string; source: SourceLike; pages?: string }) {
  const label = `${source.display_id}${source.version_number ? ` v${source.version_number}` : ''}${pages ? ` · ${pages}` : ''}`
  const href = sourceHref(caseId, source)
  return href ? (
    <Anchor component={Link} to={href} ff="monospace" size="xs" fw={600}>
      {label}
    </Anchor>
  ) : (
    <Text span ff="monospace" size="xs" fw={600}>
      {label}
    </Text>
  )
}

export function Notices({ notices }: { notices: string[] }) {
  if (!notices.length) return null
  return (
    <Alert color="gray" variant="light" p="xs" icon={<IconInfoCircle size={16} />}>
      <Stack gap={2}>
        {notices.map((n) => (
          <Text key={n} size="xs">
            {n}
          </Text>
        ))}
      </Stack>
    </Alert>
  )
}

export function Relevance({ value }: { value: number }) {
  return (
    <Tooltip label="Orders the results for this investigation. Not a probability, and not proof that the cases are alike.">
      <Stack gap={2} w={120} style={{ cursor: 'help' }}>
        <Group justify="space-between" gap={4}>
          <Text size="10px" c="dimmed" tt="uppercase" fw={600}>
            Relevance
          </Text>
          <Text size="xs" fw={700} ff="monospace">
            {value}
          </Text>
        </Group>
        <Progress value={value} size="sm" color="hawk" aria-label={`Relevance ${value} out of 100`} />
      </Stack>
    </Tooltip>
  )
}

/** What of the case Case Intelligence has read for you, and what it can't read. */
export function CoverageBar({ coverage, onPrepare, preparing }: { coverage?: Coverage; onPrepare: () => void; preparing: boolean }) {
  if (!coverage) return null
  const waiting = coverage.pending.length + (coverage.notes - coverage.notes_indexed)
  const needsWork = waiting > 0 || coverage.passages_without_meaning > 0
  const skipped = [...coverage.not_readable, ...coverage.unreadable]
  return (
    <Paper withBorder p="xs" radius="sm">
      <Group justify="space-between" gap="xs" wrap="wrap">
        <Group gap={8} wrap="wrap">
          <IconBook2 size={16} style={{ color: 'var(--mantine-color-hawk-4)' }} aria-hidden />
          <Text size="sm">
            Read for you: <b>{coverage.indexed}</b> of {coverage.readable} readable document
            {coverage.readable === 1 ? '' : 's'}, <b>{coverage.notes_indexed}</b> of {coverage.notes} note{coverage.notes === 1 ? '' : 's'} ·{' '}
            {coverage.passages} passage{coverage.passages === 1 ? '' : 's'}
          </Text>
          {coverage.pending.length > 0 && (
            <Tooltip label={coverage.pending.join(', ')}>
              <Badge color="orange" variant="light" size="sm">
                {coverage.pending.length} waiting to be read
              </Badge>
            </Tooltip>
          )}
          {coverage.no_text.length > 0 && (
            <Tooltip label={`${coverage.no_text.join(', ')}: no text found (scanned pages need text recognition, not available yet)`}>
              <Badge color="gray" variant="light" size="sm">
                {coverage.no_text.length} without text
              </Badge>
            </Tooltip>
          )}
          {skipped.length > 0 && (
            <Tooltip
              multiline
              w={340}
              label={
                <List size="xs" spacing={2}>
                  {skipped.map((s) => (
                    <List.Item key={s.display_id}>
                      {s.display_id}: {s.reason}
                    </List.Item>
                  ))}
                </List>
              }
            >
              <Badge color={coverage.unreadable.length ? 'red' : 'gray'} variant="light" size="sm" leftSection={coverage.unreadable.length ? <IconAlertTriangle size={11} /> : undefined}>
                {skipped.length} not read
              </Badge>
            </Tooltip>
          )}
          {coverage.passages_without_meaning > 0 && (
            <Tooltip label="These passages are found by their words only until their meaning has been computed.">
              <Badge color="gray" variant="outline" size="sm">
                {coverage.passages_without_meaning} found by words only
              </Badge>
            </Tooltip>
          )}
        </Group>
        {needsWork && (
          <Button size="compact-xs" variant="light" leftSection={<IconRefresh size={12} />} loading={preparing} onClick={onPrepare}>
            Read now
          </Button>
        )}
      </Group>
      <Text size="xs" c="dimmed" mt={4}>
        Only what you may see is read for you: sealed exhibits and anything above your clearance never reach results or answers.
      </Text>
    </Paper>
  )
}
