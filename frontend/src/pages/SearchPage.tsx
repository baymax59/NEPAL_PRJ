import {
  Button,
  Chip,
  Group,
  Loader,
  MultiSelect,
  NumberInput,
  Pagination,
  SegmentedControl,
  Select,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
  Title,
} from '@mantine/core'
import { IconSearch } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { getFilterOptions, listCases, search } from '../api/endpoints'
import type { SearchHit, SearchMode, SearchRequest } from '../api/types'
import { SearchResultCard } from '../components/CaseCards'
import { ErrorAlert, Notices, RelevanceNote, StatTile } from '../components/common'

const PAGE_SIZE = 10
const LAST_SEARCH_KEY = 'case-search.last-search'
const EXAMPLES = [
  'illegal building ordered to be pulled down',
  'retired government servant denied pension arrears',
  'murder conviction based only on circumstantial evidence',
  'can the accused get pre-arrest bail',
  'quashing of FIR in a business dispute',
]

interface SearchState {
  query: string
  mode: SearchMode
  yearFrom: number | null
  yearTo: number | null
  outcomes: string[]
  page: number
}

const EMPTY: SearchState = { query: '', mode: 'hybrid', yearFrom: null, yearTo: null, outcomes: [], page: 1 }

// Kept for this browser tab only (so "back to results" works); never put in the URL.
function loadLastSearch(): SearchState | null {
  try {
    const saved = sessionStorage.getItem(LAST_SEARCH_KEY)
    return saved ? { ...EMPTY, ...(JSON.parse(saved) as SearchState) } : null
  } catch {
    return null
  }
}

function saveLastSearch(state: SearchState) {
  try {
    sessionStorage.setItem(LAST_SEARCH_KEY, JSON.stringify(state))
  } catch {
    // storage unavailable: the search still works, it just isn't remembered
  }
}

type SortOrder = 'relevance' | 'newest' | 'oldest'

function sortHits(hits: SearchHit[], order: SortOrder): SearchHit[] {
  if (order === 'relevance') return hits
  const sign = order === 'newest' ? -1 : 1
  return [...hits].sort((a, b) => {
    const x = a.case.primary_date
    const y = b.case.primary_date
    if (x === y) return 0
    if (x === null) return 1 // unknown dates last
    if (y === null) return -1
    return x < y ? -sign : sign
  })
}

export function SearchPage() {
  const [remembered] = useState(loadLastSearch)
  const [form, setForm] = useState<SearchState>(remembered ?? EMPTY)
  const [submitted, setSubmitted] = useState<SearchState | null>(remembered)
  const [sort, setSort] = useState<SortOrder>('relevance')

  const filters = useQuery({ queryKey: ['filter-options'], queryFn: getFilterOptions })
  const total = useQuery({ queryKey: ['case-count'], queryFn: () => listCases({ limit: 1 }) })

  const request: SearchRequest | null = submitted
    ? {
        query: submitted.query,
        mode: submitted.mode,
        filters: { year_from: submitted.yearFrom, year_to: submitted.yearTo, outcome: submitted.outcomes },
        limit: PAGE_SIZE,
        offset: (submitted.page - 1) * PAGE_SIZE,
      }
    : null
  const results = useQuery({
    queryKey: ['search', request],
    queryFn: () => search(request as SearchRequest),
    enabled: request !== null,
  })

  function run(state: SearchState) {
    if (!state.query.trim()) return
    saveLastSearch(state)
    setSubmitted(state)
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    const next = { ...form, page: 1 }
    setForm(next)
    run(next)
  }

  const withOutcome = filters.data?.outcomes.reduce((sum, o) => sum + o.count, 0)
  const years = filters.data?.years

  return (
    <Stack gap="lg">
      <SimpleGrid cols={{ base: 2, md: 4 }}>
        <StatTile label="Cases in the collection" value={total.data?.total ?? '…'} hint="that you are cleared to see" />
        <StatTile label="Years covered" value={years ? `${years.min}–${years.max}` : '…'} hint="by decision date" />
        <StatTile
          label="With a recorded outcome"
          value={withOutcome ?? '…'}
          hint={total.data && withOutcome !== undefined ? `of ${total.data.total}` : undefined}
        />
        <StatTile
          label="Most common outcome"
          value={<Text component="span" fz={20} fw={600}>{filters.data?.outcomes[0]?.value ?? '…'}</Text>}
          hint={filters.data?.outcomes[0] ? `${filters.data.outcomes[0].count} cases` : undefined}
        />
      </SimpleGrid>

      <form onSubmit={submit}>
        <Stack gap="sm">
          <Title order={1} size="h3">
            Find similar historical cases
          </Title>
          <Group align="flex-end" wrap="nowrap">
            <TextInput
              flex={1}
              size="md"
              placeholder="Describe the case, or type legal terms, provisions or names"
              aria-label="Search"
              value={form.query}
              onChange={(e) => setForm({ ...form, query: e.currentTarget.value })}
              maxLength={500}
            />
            <Button type="submit" size="md" leftSection={<IconSearch size={18} />}>
              Search
            </Button>
          </Group>
          <Group gap="xs">
            <Text size="xs" c="dimmed">
              Try:
            </Text>
            {EXAMPLES.map((example) => (
              <Chip
                key={example}
                size="xs"
                checked={false}
                onClick={() => {
                  const next = { ...form, query: example, page: 1 }
                  setForm(next)
                  run(next)
                }}
              >
                {example}
              </Chip>
            ))}
          </Group>
          <Group align="flex-end" gap="md">
            <div>
              <Text size="sm" fw={500} mb={4}>
                Search by
              </Text>
              <SegmentedControl
                size="xs"
                value={form.mode}
                onChange={(value) => setForm({ ...form, mode: value as SearchMode })}
                data={[
                  { label: 'Words + meaning', value: 'hybrid' },
                  { label: 'Exact words', value: 'keyword' },
                  { label: 'Meaning only', value: 'semantic' },
                ]}
              />
            </div>
            <NumberInput
              label="Decided from"
              placeholder={years ? String(years.min) : 'Year'}
              w={120}
              size="xs"
              min={1900}
              max={2100}
              value={form.yearFrom ?? ''}
              onChange={(v) => setForm({ ...form, yearFrom: typeof v === 'number' ? v : null })}
            />
            <NumberInput
              label="to"
              placeholder={years ? String(years.max) : 'Year'}
              w={120}
              size="xs"
              min={1900}
              max={2100}
              value={form.yearTo ?? ''}
              onChange={(v) => setForm({ ...form, yearTo: typeof v === 'number' ? v : null })}
            />
            <MultiSelect
              label="Recorded outcome"
              placeholder="Any outcome"
              size="xs"
              miw={220}
              clearable
              data={(filters.data?.outcomes ?? []).map((o) => ({ value: o.value, label: `${o.value} (${o.count})` }))}
              value={form.outcomes}
              onChange={(outcomes) => setForm({ ...form, outcomes })}
            />
          </Group>
          <Text size="xs" c="dimmed">
            Use "quotes" for an exact phrase, -word to exclude a word, and OR (in capitals) for alternatives.
          </Text>
        </Stack>
      </form>

      {results.isFetching && (
        <Group>
          <Loader size="sm" />
          <Text size="sm" c="dimmed">
            Searching…
          </Text>
        </Group>
      )}
      {results.error && <ErrorAlert error={results.error} />}
      {results.data && submitted && (
        <Stack gap="md">
          <Group justify="space-between">
            <Text fw={500}>
              {results.data.total_cases} {results.data.total_cases === 1 ? 'case' : 'cases'} found
            </Text>
            <Select
              size="xs"
              w={200}
              aria-label="Sort results on this page"
              value={sort}
              onChange={(value) => setSort((value as SortOrder) ?? 'relevance')}
              data={[
                { value: 'relevance', label: 'Sort: relevance' },
                { value: 'newest', label: 'Sort: newest decision' },
                { value: 'oldest', label: 'Sort: oldest decision' },
              ]}
              allowDeselect={false}
            />
          </Group>
          <Notices notices={results.data.notices} />
          {results.data.results.length > 0 && <RelevanceNote note={results.data.relevance_note} />}
          {sortHits(results.data.results, sort).map((hit) => (
            <SearchResultCard
              key={hit.case.display_id}
              hit={hit}
              query={results.data.query}
              note={results.data.relevance_note}
            />
          ))}
          {results.data.total_cases > PAGE_SIZE && (
            <Pagination
              total={Math.ceil(results.data.total_cases / PAGE_SIZE)}
              value={submitted.page}
              onChange={(page) => run({ ...submitted, page })}
            />
          )}
        </Stack>
      )}
    </Stack>
  )
}
