// Search inside the case as it stands now: words (with "quoted phrases", -excluded words, OR) and meaning.

import { Badge, Button, Group, Paper, SegmentedControl, Stack, Text, TextInput } from '@mantine/core'
import { IconSearch } from '@tabler/icons-react'
import { useMutation } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { SnippetText } from '../../../components/SnippetText'
import { kh } from '../../api'
import { toastError } from '../../feedback'
import type { CaseDetail, CaseSearchResponse } from '../../types'
import { EmptyState } from '../../ui'
import { Notices, SourceLink } from './common'
import { kindLabel, pageText } from './format'

const MODES = [
  { value: 'hybrid', label: 'Words and meaning' },
  { value: 'keyword', label: 'Exact words' },
  { value: 'semantic', label: 'Meaning' },
]

function Results({ caseId, result }: { caseId: string; result: CaseSearchResponse }) {
  return (
    <Stack gap="sm">
      <Notices notices={result.notices} />
      <Text size="sm" c="dimmed">
        {result.total_sources} document{result.total_sources === 1 ? '' : 's'} and notes, {result.total_passages} passage
        {result.total_passages === 1 ? '' : 's'}
      </Text>
      {result.results.length === 0 && result.notices.length === 0 && (
        <Paper withBorder>
          <EmptyState title="Nothing found">Try other words, or "Meaning" to find passages that say the same in other words.</EmptyState>
        </Paper>
      )}
      {result.results.map((r) => (
        <Paper key={r.source.path} withBorder p="sm" radius="sm">
          <Group justify="space-between" gap="xs" wrap="wrap">
            <Group gap={6} wrap="wrap">
              <SourceLink caseId={caseId} source={r.source} />
              <Badge size="xs" variant="light" color={r.source.kind === 'evidence' ? 'hawk' : 'gray'}>
                {kindLabel(r.source.kind, r.source.artifact_type)}
              </Badge>
              <Text size="sm" fw={500}>
                {r.source.title}
              </Text>
            </Group>
            <Text size="xs" c="dimmed">
              {r.matching_passages} matching passage{r.matching_passages === 1 ? '' : 's'}
            </Text>
          </Group>
          <Text size="xs" c="dimmed" ff="monospace">
            {r.source.path}
            {r.also_in.length > 0 && ` · the same file is also ${r.also_in.map((s) => s.display_id).join(', ')}`}
          </Text>
          <Stack gap={6} mt={6}>
            {r.passages.map((p) => (
              <Group key={p.chunk_id} gap="xs" align="flex-start" wrap="nowrap">
                <Stack gap={2} w={72} style={{ flexShrink: 0 }}>
                  <Text size="xs" ff="monospace" c="dimmed">
                    {pageText(p.page_start, p.page_end) || '—'}
                  </Text>
                  {p.matched_by.map((m) => (
                    <Badge key={m} size="xs" variant="outline" color={m === 'keyword' ? 'yellow' : 'violet'}>
                      {m === 'keyword' ? 'words' : 'meaning'}
                    </Badge>
                  ))}
                </Stack>
                <SnippetText parts={p.snippet} />
              </Group>
            ))}
          </Stack>
        </Paper>
      ))}
    </Stack>
  )
}

export function SearchView({ detail }: { detail: CaseDetail }) {
  const [text, setText] = useState('')
  const [mode, setMode] = useState('hybrid')
  const search = useMutation({
    mutationFn: (query: string) => kh.searchCase(detail.id, { query, mode: mode as 'hybrid', limit: 20 }),
    onError: (error) => toastError(error, 'Search failed'),
  })
  function submit(event: FormEvent) {
    event.preventDefault()
    if (text.trim()) search.mutate(text.trim())
  }
  return (
    <Stack gap="sm">
      <form onSubmit={submit}>
        <Group gap="xs" align="flex-end" wrap="wrap">
          <TextInput
            label="Search this case"
            description='Words are matched by their stem; use "quotes" for a phrase or a number, -word to exclude, OR for alternatives.'
            placeholder='e.g. "98450 12345" or caller pretending to be a bank officer'
            value={text}
            onChange={(e) => setText(e.currentTarget.value)}
            maxLength={500}
            style={{ flex: 1, minWidth: 260 }}
          />
          <SegmentedControl size="xs" data={MODES} value={mode} onChange={setMode} />
          <Button type="submit" leftSection={<IconSearch size={16} />} loading={search.isPending} disabled={!text.trim()}>
            Search
          </Button>
        </Group>
      </form>
      {search.data && <Results caseId={detail.id} result={search.data} />}
    </Stack>
  )
}
