// AI-powered CDR search — data-aware: AI reads the actual uploaded file contents.

import {
  Badge,
  Box,
  Button,
  Code,
  Group,
  Paper,
  SimpleGrid,
  Skeleton,
  Stack,
  Table,
  Text,
  Textarea,
  Title,
} from '@mantine/core'
import {
  IconBrain,
  IconChevronDown,
  IconChevronUp,
  IconDatabase,
  IconRobot,
  IconSearch,
} from '@tabler/icons-react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { kh } from '../../api'
import type { CdrRecord } from '../../types'
import { EmptyState } from '../../ui'

interface Props {
  caseId: string
}

const EXAMPLES = [
  'Who called the most?',
  'What numbers are in the data?',
  'What is the date range of this file?',
  'Show all outgoing voice calls',
  'SMS messages only',
  'Calls longer than 5 minutes',
  'Show incoming calls',
  'Are there any IMEI numbers?',
]

function formatDur(secs: number | null | undefined) {
  if (secs == null) return '—'
  if (secs < 60) return `${secs}s`
  return `${Math.floor(secs / 60)}m ${secs % 60}s`
}

function dirBadge(dir: CdrRecord['call_direction']) {
  if (!dir) return null
  return (
    <Badge size="xs" variant="light" color={dir === 'incoming' ? 'blue' : 'green'}>
      {dir === 'incoming' ? '← in' : 'out →'}
    </Badge>
  )
}

export function CdrLlmSearchPanel({ caseId }: Props) {
  const [query, setQuery] = useState('')
  const [filtersOpen, setFiltersOpen] = useState(false)

  // Load data profile so the AI (and the user) knows what's in the file
  const profileQuery = useQuery({
    queryKey: ['kh', 'cdr', caseId, 'data-profile'],
    queryFn: () => kh.cdrDataProfile(caseId),
    staleTime: 60_000,
  })
  const profile = profileQuery.data

  const mutation = useMutation({
    mutationFn: (q: string) => kh.cdrLlmSearch(caseId, q),
  })

  const run = () => {
    if (query.trim().length >= 3) mutation.mutate(query.trim())
  }

  return (
    <Stack gap="md">
      <Stack gap={4}>
        <Title order={5} fw={600}>AI CDR Search</Title>
        <Text size="sm" c="dimmed">
          Ask anything about the uploaded CDR data in plain language. The AI reads
          the actual file contents and answers directly or filters the records for you.
        </Text>
      </Stack>

      {/* Data profile banner — shows what AI knows about the file */}
      {profileQuery.isLoading && <Skeleton height={72} radius="sm" />}
      {profile && profile.has_data && (
        <Paper withBorder p="sm" radius="sm" bg="var(--mantine-color-default-hover)">
          <Group gap="xs" mb={6}>
            <IconDatabase size={14} />
            <Text size="xs" fw={600} tt="uppercase" c="dimmed">AI knows about this file</Text>
          </Group>
          <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="xs">
            <Box>
              <Text size="xs" c="dimmed">Records</Text>
              <Text size="sm" fw={600}>{profile.total_records.toLocaleString()}</Text>
            </Box>
            <Box>
              <Text size="xs" c="dimmed">Numbers</Text>
              <Text size="sm" fw={600}>{profile.unique_number_count.toLocaleString()}</Text>
            </Box>
            <Box>
              <Text size="xs" c="dimmed">Date range</Text>
              <Text size="sm" fw={600}>
                {profile.date_range
                  ? `${profile.date_range.earliest} → ${profile.date_range.latest}`
                  : '—'}
              </Text>
            </Box>
            <Box>
              <Text size="xs" c="dimmed">Service types</Text>
              <Text size="sm" fw={600}>
                {Object.keys(profile.service_type_counts).join(', ') || '—'}
              </Text>
            </Box>
          </SimpleGrid>
          {profile.top_numbers.length > 0 && (
            <Box mt={6}>
              <Text size="xs" c="dimmed">Top numbers: </Text>
              <Group gap={4} mt={2} wrap="wrap">
                {profile.top_numbers.slice(0, 8).map((n) => (
                  <Badge
                    key={n.number}
                    size="xs"
                    variant="outline"
                    ff="monospace"
                    style={{ cursor: 'pointer' }}
                    onClick={() => setQuery(`Show timeline for ${n.number}`)}
                  >
                    {n.number} ({n.event_count})
                  </Badge>
                ))}
              </Group>
            </Box>
          )}
        </Paper>
      )}

      {/* Example questions */}
      <Paper withBorder p="sm" radius="sm">
        <Text size="xs" c="dimmed" mb={6} fw={500}>Try asking:</Text>
        <Group gap={6} wrap="wrap">
          {EXAMPLES.map((ex) => (
            <Badge
              key={ex}
              variant="light"
              color="hawk"
              size="sm"
              style={{ cursor: 'pointer', userSelect: 'none' }}
              onClick={() => { setQuery(ex); mutation.reset() }}
            >
              {ex}
            </Badge>
          ))}
        </Group>
      </Paper>

      {/* Input */}
      <Textarea
        label="Your question"
        placeholder="e.g. Who are the top 5 numbers by call volume? Or: Show me all SMS after midnight."
        value={query}
        onChange={(e) => { setQuery(e.currentTarget.value); if (mutation.data) mutation.reset() }}
        autosize
        minRows={2}
        maxRows={5}
        size="sm"
      />

      <Group gap="xs">
        <Button
          size="sm"
          leftSection={<IconBrain size={14} />}
          onClick={run}
          loading={mutation.isPending}
          disabled={query.trim().length < 3}
        >
          {mutation.isPending ? 'Thinking…' : 'Ask AI'}
        </Button>
        {mutation.data && (
          <Button size="sm" variant="subtle" onClick={() => { mutation.reset(); setFiltersOpen(false) }}>
            Clear
          </Button>
        )}
      </Group>

      {/* Error */}
      {mutation.isError && (
        <Paper withBorder p="md" radius="sm" style={{ borderColor: 'var(--mantine-color-red-4)' }}>
          <Group gap="xs" mb={4}>
            <IconRobot size={16} color="var(--mantine-color-red-6)" />
            <Text size="sm" fw={600} c="red">AI search failed</Text>
          </Group>
          <Text size="sm" c="dimmed">
            {mutation.error instanceof Error
              ? mutation.error.message
              : 'Could not reach Ollama. Make sure it is running with a model loaded.'}
          </Text>
        </Paper>
      )}

      {/* Results */}
      {mutation.data && (
        <Stack gap="md">

          {/* AI response — always shown first */}
          <Paper
            withBorder
            p="md"
            radius="sm"
            style={{ borderLeft: '3px solid var(--mantine-color-hawk-5)' }}
          >
            <Group gap="xs" mb="xs">
              <IconRobot size={16} />
              <Text size="sm" fw={600}>AI Response</Text>
              {mutation.data.mode === 'direct' && (
                <Badge size="xs" color="grape" variant="light">Direct answer</Badge>
              )}
              {mutation.data.mode === 'filter' && mutation.data.total > 0 && (
                <Badge size="xs" color="hawk" variant="light">
                  {mutation.data.total} record{mutation.data.total !== 1 ? 's' : ''} found
                </Badge>
              )}
            </Group>
            <Text size="sm" style={{ lineHeight: 1.65, whiteSpace: 'pre-wrap' }}>
              {mutation.data.narrative}
            </Text>
          </Paper>

          {/* Filters panel (filter mode only) */}
          {mutation.data.mode === 'filter' && (
            <Paper withBorder radius="sm">
              <Group
                px="sm"
                py="xs"
                style={{ cursor: 'pointer' }}
                onClick={() => setFiltersOpen((o) => !o)}
                justify="space-between"
              >
                <Group gap="xs">
                  <IconSearch size={14} />
                  <Text size="sm" fw={500}>Filters used</Text>
                  {Object.keys(mutation.data.filters).length === 0 && (
                    <Badge size="xs" color="gray" variant="outline">none — all records</Badge>
                  )}
                </Group>
                {filtersOpen ? <IconChevronUp size={14} /> : <IconChevronDown size={14} />}
              </Group>
              {filtersOpen && (
                <Box px="sm" pb="sm">
                  <Code block style={{ fontSize: 11 }}>
                    {JSON.stringify(mutation.data.filters, null, 2)}
                  </Code>
                </Box>
              )}
            </Paper>
          )}

          {/* Data table (filter mode with results) */}
          {mutation.data.mode === 'filter' && (
            mutation.data.total === 0 ? (
              <EmptyState title="No records matched">
                The filters did not match any CDR records. Try a different question.
              </EmptyState>
            ) : (
              <Paper withBorder radius="sm">
                <Group px="sm" py="xs" gap="xs">
                  <Text size="sm" fw={600}>Matching CDR Records</Text>
                  <Badge>{mutation.data.total}</Badge>
                  {mutation.data.items.length < mutation.data.total && (
                    <Text size="xs" c="dimmed">
                      showing first {mutation.data.items.length}
                    </Text>
                  )}
                </Group>
                <Box style={{ overflowX: 'auto' }}>
                  <Table striped highlightOnHover withColumnBorders>
                    <Table.Thead>
                      <Table.Tr>
                        <Table.Th>Time (UTC)</Table.Th>
                        <Table.Th>A-Party</Table.Th>
                        <Table.Th>B-Party</Table.Th>
                        <Table.Th>Dir</Table.Th>
                        <Table.Th>Service</Table.Th>
                        <Table.Th>Duration</Table.Th>
                        <Table.Th>Cell ID</Table.Th>
                      </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                      {mutation.data.items.map((r: CdrRecord) => (
                        <Table.Tr key={r.id}>
                          <Table.Td>
                            <Text size="xs" ff="monospace">
                              {r.timestamp_utc
                                ? new Date(r.timestamp_utc).toLocaleString()
                                : '—'}
                            </Text>
                          </Table.Td>
                          <Table.Td>
                            <Text size="xs" ff="monospace">
                              {r.a_party_canonical ?? r.a_party ?? '—'}
                            </Text>
                          </Table.Td>
                          <Table.Td>
                            <Text size="xs" ff="monospace">
                              {r.b_party_canonical ?? r.b_party ?? '—'}
                            </Text>
                          </Table.Td>
                          <Table.Td>{dirBadge(r.call_direction)}</Table.Td>
                          <Table.Td>
                            {r.service_type && (
                              <Badge
                                size="xs"
                                variant="outline"
                                color={
                                  r.service_type === 'voice'
                                    ? 'teal'
                                    : r.service_type === 'sms'
                                      ? 'orange'
                                      : 'grape'
                                }
                              >
                                {r.service_type}
                              </Badge>
                            )}
                          </Table.Td>
                          <Table.Td>
                            <Text size="xs">{formatDur(r.duration_seconds)}</Text>
                          </Table.Td>
                          <Table.Td>
                            <Text size="xs" ff="monospace">{r.cell_id ?? '—'}</Text>
                          </Table.Td>
                        </Table.Tr>
                      ))}
                    </Table.Tbody>
                  </Table>
                </Box>
              </Paper>
            )
          )}
        </Stack>
      )}
    </Stack>
  )
}
