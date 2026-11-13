import {
  Alert,
  Anchor,
  Badge,
  Button,
  Center,
  Group,
  List,
  Loader,
  Paper,
  SimpleGrid,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
  Tooltip,
} from '@mantine/core'
import {
  IconArrowLeft,
  IconExternalLink,
  IconInfoCircle,
  IconMessageChatbot,
  IconPrinter,
  IconSearch,
  IconStack2,
} from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { useState, type FormEvent, type ReactNode } from 'react'
import { Link, useLocation, useParams } from 'react-router'
import { explainCase, getCase } from '../api/endpoints'
import type { CaseDetail, MatchExplanation } from '../api/types'
import { CaseAssistant } from '../components/CaseAssistant'
import { CaseFacts } from '../components/CaseCards'
import { ErrorAlert, Notices, Section, Value } from '../components/common'
import { SnippetText } from '../components/SnippetText'
import { fieldName, formatDate, formatDateTime, pageLabel, sentenceCase } from '../lib/format'

const SECTIONS = [
  ['identification', 'A. Identification'],
  ['overview', 'B. Overview'],
  ['timeline', 'C. Timeline'],
  ['outcome', 'D. Outcome'],
  ['similarity', 'E. Similarity analysis'],
  ['documents', 'F. Documents'],
  ['quality', 'G. Data quality and provenance'],
  ['actions', 'H. Actions'],
] as const

const REFERENCE_LABELS: Record<string, string> = {
  cnr: 'CNR',
  neutral_citation: 'Neutral citation',
  citation: 'Report citation',
}

function Rows({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <Table variant="vertical" layout="fixed" withTableBorder={false}>
      <Table.Tbody>
        {rows.map(([label, value]) => (
          <Table.Tr key={label}>
            <Table.Th w={220}>{label}</Table.Th>
            <Table.Td>{value}</Table.Td>
          </Table.Tr>
        ))}
      </Table.Tbody>
    </Table>
  )
}

function Identification({ detail }: { detail: CaseDetail }) {
  return (
    <Rows
      rows={[
        ['Case ID', detail.display_id],
        ['Title', <Value key="t">{detail.title}</Value>],
        ['Category', <Value key="c">{detail.category}</Value>],
        ['Court', <Value key="ct">{detail.court_or_agency}</Value>],
        ['Status', <Value key="s">{detail.status}</Value>],
        ['Source system', detail.source_system],
        ['Record ID in source', detail.source_record_id],
        ...Object.entries(detail.reference_numbers).map(([kind, number]): [string, ReactNode] => [
          REFERENCE_LABELS[kind] ?? sentenceCase(kind),
          number,
        ]),
        ...detail.dates.map((d): [string, ReactNode] => [
          `${sentenceCase(d.kind)} date`,
          <span key={d.kind}>
            {formatDate(d.value)}{' '}
            <Text span size="xs" c="dimmed">
              (from {d.source_field})
            </Text>
          </span>,
        ]),
      ]}
    />
  )
}

function Overview({ detail }: { detail: CaseDetail }) {
  const people = (role: string) => detail.parties.filter((p) => p.role === role).map((p) => p.name)
  return (
    <Stack gap="md">
      <Rows
        rows={[
          ['Summary (as recorded)', <Value key="s">{detail.summary}</Value>],
          ['Petitioner(s)', <Value key="p">{people('petitioner').join('; ')}</Value>],
          ['Respondent(s)', <Value key="r">{people('respondent').join('; ')}</Value>],
          ['Judges', <Value key="j">{detail.officials.map((o) => o.name).join(', ')}</Value>],
        ]}
      />
      <div>
        <Text fw={500} size="sm">
          Courts and tribunals named
        </Text>
        <Text size="xs" c="dimmed" mb="xs">
          Detected automatically from the judgment text.
        </Text>
        {detail.courts.length === 0 ? (
          <Value>{null}</Value>
        ) : (
          <Group gap="xs">
            {detail.courts.map((court) => (
              <Tooltip
                key={court.name}
                label={`Named ${court.mentions}× on ${court.pages.length ? `pages ${court.pages.join(', ')}` : 'pages not recorded'}`}
              >
                <Badge variant="light" color="gray" tt="none">
                  {court.name} · {court.mentions}
                </Badge>
              </Tooltip>
            ))}
          </Group>
        )}
      </div>
      <div>
        <Text fw={500} size="sm">
          Statutory provisions cited
        </Text>
        <Text size="xs" c="dimmed" mb="xs">
          Detected automatically from the judgment text. Check the cited pages; unusual citation styles can be
          missed.
        </Text>
        {detail.provisions.length === 0 ? (
          <Value>{null}</Value>
        ) : (
          <Group gap="xs">
            {detail.provisions.slice(0, 20).map((p) => (
              <Tooltip key={p.key} label={`Cited ${p.mentions}× on ${p.pages.length ? `pages ${p.pages.join(', ')}` : 'pages not recorded'}`}>
                <Badge variant="light" color="gray" tt="none">
                  {p.label} · {p.mentions}
                </Badge>
              </Tooltip>
            ))}
          </Group>
        )}
      </div>
    </Stack>
  )
}

const EVENT_LABELS: Record<string, string> = {
  judgment: 'Judgment',
  order_under_appeal: 'Order under appeal',
  dated_mention: 'Mentioned in text',
  other: 'Event',
}

function eventSource(method: string, page: number | null): string {
  if (method === 'source_field') return 'From the source record'
  const where = page ? `p. ${page}` : 'no page'
  return method === 'manual' ? `Entered manually · ${where}` : `Found automatically · ${where}`
}

function Timeline({ detail }: { detail: CaseDetail }) {
  if (detail.timeline.length === 0) {
    return (
      <Text size="sm" c="dimmed">
        No timeline has been extracted for this case yet.
      </Text>
    )
  }
  return (
    <Stack gap="xs">
      <Text size="xs" c="dimmed">
        Dates found automatically in the judgment text, each with the sentence and page it comes from. Dates of earlier
        cases cited in the judgment are filtered out where recognisable, but some may remain: check the page before
        relying on an entry.
      </Text>
      <Table verticalSpacing="xs">
        <Table.Thead>
          <Table.Tr>
            <Table.Th w={120}>Date</Table.Th>
            <Table.Th w={160}>Type</Table.Th>
            <Table.Th>Event</Table.Th>
            <Table.Th w={180}>Source</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {detail.timeline.map((event, index) => (
            <Table.Tr key={index}>
              <Table.Td style={{ whiteSpace: 'nowrap' }}>{formatDate(event.event_date) ?? event.date_text ?? '—'}</Table.Td>
              <Table.Td>
                <Badge
                  size="sm"
                  tt="none"
                  color="gray"
                  variant={event.event_type === 'dated_mention' ? 'outline' : 'light'}
                >
                  {EVENT_LABELS[event.event_type] ?? event.event_type}
                </Badge>
              </Table.Td>
              <Table.Td>
                <Text size="sm">{event.description}</Text>
              </Table.Td>
              <Table.Td>
                <Text size="xs" c="dimmed">
                  {eventSource(event.extraction_method, event.page_number)}
                </Text>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Stack>
  )
}

function Outcome({ detail }: { detail: CaseDetail }) {
  return (
    <Rows
      rows={[
        ['Recorded outcome', <Value key="o">{detail.outcome}</Value>],
        ['Taken from', <Value key="f">{detail.outcome_source_field && `source field "${detail.outcome_source_field}"`}</Value>],
        ['Date', <Value key="d">{formatDate(detail.outcome_date)}</Value>],
        [
          'Time to resolution',
          <Text key="t" size="sm" c="dimmed" fs="italic">
            Cannot be calculated: the source does not record when the case was filed.
          </Text>,
        ],
      ]}
    />
  )
}

function ExplanationView({ data }: { data: MatchExplanation }) {
  return (
    <Stack gap="md">
      <Notices notices={data.notices} />
      <SimpleGrid cols={{ base: 1, md: 2 }}>
        <div>
          <Text fw={500} size="sm" mb={4}>
            Why it matches
          </Text>
          <List size="sm" spacing={2}>
            {data.reasons.map((r) => (
              <List.Item key={r}>{r}</List.Item>
            ))}
          </List>
        </div>
        <div>
          <Text fw={500} size="sm" mb={4}>
            Differences
          </Text>
          {data.differences.length ? (
            <List size="sm" spacing={2}>
              {data.differences.map((d) => (
                <List.Item key={d}>{d}</List.Item>
              ))}
            </List>
          ) : (
            <Text size="sm" c="dimmed">
              None found in the words and provisions of the search.
            </Text>
          )}
        </div>
      </SimpleGrid>
      {data.shared_terms.length > 0 && (
        <Group gap="xs">
          <Text size="sm" fw={500}>
            Shared words:
          </Text>
          {data.shared_terms.map((t) => (
            <Badge key={t.term} variant="light" tt="none">
              {t.term} · {t.passages} passages
            </Badge>
          ))}
        </Group>
      )}
      {data.shared_provisions.length > 0 && (
        <Group gap="xs">
          <Text size="sm" fw={500}>
            Shared provisions:
          </Text>
          {data.shared_provisions.map((p) => (
            <Badge key={p.key} variant="light" tt="none">
              {p.label} · pages {p.pages.join(', ')}
            </Badge>
          ))}
        </Group>
      )}
      {data.passages.length > 0 && (
        <Stack gap="xs">
          <Text fw={500} size="sm">
            Closest passages
          </Text>
          {data.passages.map((p) => (
            <Paper key={p.chunk_id} withBorder p="sm" radius="sm">
              <Text size="xs" c="dimmed" mb={4}>
                {pageLabel(p.page_start, p.page_end)} · matched by {p.matched_by.join(' and ')}
                {p.similarity !== null && ` · similarity ${p.similarity.toFixed(2)}`}
              </Text>
              <SnippetText parts={p.snippet} />
            </Paper>
          ))}
        </Stack>
      )}
      <Alert color="gray" variant="light" icon={<IconInfoCircle size={18} />}>
        <Text size="xs">{data.method_note}</Text>
      </Alert>
    </Stack>
  )
}

function SimilarityAnalysis({ displayId, initialQuery }: { displayId: string; initialQuery: string | null }) {
  const [text, setText] = useState(initialQuery ?? '')
  const [query, setQuery] = useState(initialQuery)
  const explanation = useQuery({
    queryKey: ['explain', displayId, query],
    queryFn: () => explainCase(displayId, query as string),
    enabled: !!query,
  })
  function submit(event: FormEvent) {
    event.preventDefault()
    if (text.trim()) setQuery(text.trim())
  }
  return (
    <Stack gap="md">
      <form onSubmit={submit}>
        <Group align="flex-end" wrap="nowrap">
          <TextInput
            flex={1}
            label="Compare this case with a description"
            description={initialQuery ? 'Filled in from your search.' : 'Describe the new case, or paste its key facts.'}
            value={text}
            onChange={(e) => setText(e.currentTarget.value)}
            maxLength={500}
          />
          <Button type="submit" variant="light" leftSection={<IconSearch size={16} />}>
            Explain match
          </Button>
        </Group>
      </form>
      {explanation.isFetching && <Loader size="sm" />}
      {explanation.error && <ErrorAlert error={explanation.error} />}
      {explanation.data && <ExplanationView data={explanation.data} />}
    </Stack>
  )
}

function Documents({ detail }: { detail: CaseDetail }) {
  return (
    <Table>
      <Table.Thead>
        <Table.Tr>
          <Table.Th>Document</Table.Th>
          <Table.Th>Date</Table.Th>
          <Table.Th>Pages</Table.Th>
          <Table.Th>Text extraction</Table.Th>
          <Table.Th>Original</Table.Th>
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {detail.documents.map((doc) => (
          <Table.Tr key={doc.id}>
            <Table.Td>
              {sentenceCase(doc.doc_type)}
              {doc.language && (
                <Text span size="xs" c="dimmed">
                  {' '}
                  ({doc.language})
                </Text>
              )}
            </Table.Td>
            <Table.Td>
              <Value>{formatDate(doc.doc_date)}</Value>
            </Table.Td>
            <Table.Td>
              <Value>{doc.page_count}</Value>
            </Table.Td>
            <Table.Td>
              <Badge variant="light" color="gray" tt="none">
                {doc.extraction_status}
              </Badge>
              {doc.extraction_warnings.map((w) => (
                <Text key={w} size="xs" c="dimmed">
                  {w}
                </Text>
              ))}
            </Table.Td>
            <Table.Td>
              <Anchor href={doc.source_uri} target="_blank" rel="noopener noreferrer" size="sm">
                Open source <IconExternalLink size={12} />
              </Anchor>
            </Table.Td>
          </Table.Tr>
        ))}
      </Table.Tbody>
    </Table>
  )
}

function DataQuality({ detail }: { detail: CaseDetail }) {
  const provenance = detail.provenance as Record<string, string | null>
  return (
    <Stack gap="md">
      <Rows
        rows={[
          ['Processing status', <Badge key="s" variant="light" color="gray" tt="none">{detail.processing_status}</Badge>],
          [
            'Not in the source record',
            detail.missing_fields.length ? detail.missing_fields.map(fieldName).join(', ') : 'Nothing missing',
          ],
          ['Import warnings', detail.warnings.length ? detail.warnings.join('; ') : 'None'],
          ['Imported by', `${provenance.connector ?? '?'} (version ${provenance.connector_version ?? '?'})`],
          ['Source retrieved', provenance.retrieved_at ? formatDateTime(provenance.retrieved_at) : '—'],
          ['Source file', <Text key="u" size="sm" style={{ wordBreak: 'break-all' }}>{provenance.source_uri ?? '—'}</Text>],
          ['Record created / updated', `${formatDateTime(detail.created_at)} / ${formatDateTime(detail.updated_at)}`],
        ]}
      />
      {detail.attribution && (
        <Text size="xs" c="dimmed">
          Source: {detail.attribution}
        </Text>
      )}
    </Stack>
  )
}

export function CaseDetailsPage() {
  const { displayId = '' } = useParams()
  const location = useLocation()
  const searchQuery = (location.state as { query?: string } | null)?.query ?? null
  const detail = useQuery({ queryKey: ['case', displayId], queryFn: () => getCase(displayId) })
  const [assistantOpen, setAssistantOpen] = useState(false)

  if (detail.isPending) {
    return (
      <Center py="xl">
        <Loader />
      </Center>
    )
  }
  if (detail.error) return <ErrorAlert error={detail.error} />
  const data = detail.data

  return (
    <Stack gap="md">
      <Group justify="space-between" className="no-print">
        <Button component={Link} to="/" variant="subtle" size="xs" leftSection={<IconArrowLeft size={14} />}>
          Back to results
        </Button>
        <Button variant="light" size="xs" onClick={() => setAssistantOpen(true)} leftSection={<IconMessageChatbot size={14} />}>
          Ask the case assistant
        </Button>
      </Group>
      {/* key: a different case starts a new conversation */}
      <CaseAssistant
        key={data.display_id}
        displayId={data.display_id}
        opened={assistantOpen}
        onClose={() => setAssistantOpen(false)}
      />
      <div>
        <Title order={1} size="h3">
          {data.title ?? data.display_id}
        </Title>
        <Group gap="xs" mt={6}>
          <Badge variant="outline" color="gray" radius="sm">
            {data.display_id}
          </Badge>
          <Tooltip label="Sensitivity of this record. Only users cleared for this level (or granted access) can see it.">
            <Badge variant="light" color="gray">
              {data.sensitivity}
            </Badge>
          </Tooltip>
        </Group>
        <Paper mt="sm">
          <CaseFacts summary={data} />
        </Paper>
      </div>
      <Group gap="xs" className="no-print">
        {SECTIONS.map(([id, label]) => (
          <Anchor key={id} href={`#${id}`} size="xs">
            {label}
          </Anchor>
        ))}
      </Group>

      <Section id="identification" title="A. Identification">
        <Identification detail={data} />
      </Section>
      <Section id="overview" title="B. Overview">
        <Overview detail={data} />
      </Section>
      <Section id="timeline" title="C. Timeline">
        <Timeline detail={data} />
      </Section>
      <Section id="outcome" title="D. Outcome">
        <Outcome detail={data} />
      </Section>
      <Section id="similarity" title="E. Similarity analysis">
        <SimilarityAnalysis displayId={data.display_id} initialQuery={searchQuery} />
      </Section>
      <Section id="documents" title="F. Documents">
        <Documents detail={data} />
      </Section>
      <Section id="quality" title="G. Data quality and provenance">
        <DataQuality detail={data} />
      </Section>
      <Section id="actions" title="H. Actions">
        <Group className="no-print">
          <Button component={Link} to="/" variant="default" leftSection={<IconArrowLeft size={16} />}>
            Back to results
          </Button>
          <Button component={Link} to={`/cases/${data.display_id}/similar`} leftSection={<IconStack2 size={16} />}>
            Find and compare similar cases
          </Button>
          <Button variant="default" onClick={() => window.print()} leftSection={<IconPrinter size={16} />}>
            Print
          </Button>
          <Button variant="default" onClick={() => setAssistantOpen(true)} leftSection={<IconMessageChatbot size={16} />}>
            Ask the case assistant
          </Button>
        </Group>
      </Section>
    </Stack>
  )
}
