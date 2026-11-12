// The result cards: one per matching historical case.

import { Anchor, Badge, Button, Card, Divider, Grid, Group, List, Paper, Stack, Text, Title } from '@mantine/core'
import { IconArrowRight } from '@tabler/icons-react'
import { Link } from 'react-router'
import type { CaseSummary, SearchHit, SimilarCase } from '../api/types'
import { fieldName, formatDate, pageLabel } from '../lib/format'
import { MatchBadge, RelevanceMeter } from './common'
import { SnippetText } from './SnippetText'

/** Date, court, outcome and citation: only what the source records. */
export function CaseFacts({ summary }: { summary: CaseSummary }) {
  const decided = formatDate(summary.primary_date)
  const citation = summary.reference_numbers.neutral_citation ?? summary.reference_numbers.citation
  return (
    <Group gap="lg" wrap="wrap">
      <Text size="sm">
        <Text span c="dimmed">
          {summary.primary_date_kind === 'decision' ? 'Decided ' : 'Date '}
        </Text>
        {decided ?? (
          <Text span c="dimmed" fs="italic">
            not recorded
          </Text>
        )}
      </Text>
      {summary.court_or_agency && <Text size="sm">{summary.court_or_agency}</Text>}
      <Text size="sm">
        <Text span c="dimmed">
          Outcome{' '}
        </Text>
        {summary.outcome ?? (
          <Text span c="dimmed" fs="italic">
            no outcome recorded in the source
          </Text>
        )}
      </Text>
      {citation && (
        <Text size="sm" c="dimmed">
          {citation}
        </Text>
      )}
    </Group>
  )
}

function CardHeader({ summary, relevance, note, linkState }: {
  summary: CaseSummary
  relevance: number
  note: string
  linkState?: unknown
}) {
  return (
    <Group justify="space-between" align="flex-start" wrap="nowrap">
      <Stack gap={4}>
        <Anchor component={Link} to={`/cases/${summary.display_id}`} state={linkState} fw={600}>
          {summary.title ?? summary.display_id}
        </Anchor>
        <Group gap="xs">
          <Badge variant="outline" color="gray" size="sm" radius="sm">
            {summary.display_id}
          </Badge>
        </Group>
      </Stack>
      <RelevanceMeter value={relevance} note={note} />
    </Group>
  )
}

function MissingFields({ fields }: { fields: string[] }) {
  if (fields.length === 0) return null
  return (
    <Text size="xs" c="dimmed">
      Not in the source record: {fields.map(fieldName).join(', ')}
    </Text>
  )
}

export function SearchResultCard({ hit, query, note }: { hit: SearchHit; query: string; note: string }) {
  const best = hit.passages[0]
  // The search text travels to the details page in router state, not in the URL.
  const linkState = { query }
  return (
    <Card withBorder radius="md" padding="lg">
      <Stack gap="sm">
        <CardHeader summary={hit.case} relevance={hit.relevance} note={note} linkState={linkState} />
        <Group gap="xs">
          <MatchBadge type={hit.match_type} />
          {hit.semantic_similarity !== null && (
            <Text size="xs" c="dimmed">
              closest passage similarity {hit.semantic_similarity.toFixed(2)}
            </Text>
          )}
        </Group>
        <CaseFacts summary={hit.case} />
        {hit.reasons.length > 0 && (
          <div>
            <Text size="sm" fw={500} mb={4}>
              Why it matched
            </Text>
            <List size="sm" spacing={2}>
              {hit.reasons.map((reason) => (
                <List.Item key={reason}>{reason}</List.Item>
              ))}
            </List>
          </div>
        )}
        {best && (
          <Paper bg="var(--mantine-color-default-hover)" p="sm" radius="sm">
            <Text size="xs" c="dimmed" mb={4}>
              Best passage · {pageLabel(best.page_start, best.page_end)} · matched by {best.matched_by.join(' and ')}
            </Text>
            <SnippetText parts={best.snippet} />
          </Paper>
        )}
        <Group justify="space-between">
          <MissingFields fields={hit.case.missing_fields} />
          <Button
            component={Link}
            to={`/cases/${hit.case.display_id}`}
            state={linkState}
            variant="light"
            size="xs"
            rightSection={<IconArrowRight size={14} />}
          >
            View details
          </Button>
        </Group>
      </Stack>
    </Card>
  )
}

export function SimilarCaseCard({ item, note, newCaseLabel }: { item: SimilarCase; note: string; newCaseLabel: string }) {
  return (
    <Card withBorder radius="md" padding="lg">
      <Stack gap="sm">
        <CardHeader summary={item.case} relevance={item.relevance} note={note} />
        <Group gap="xs">
          <MatchBadge type={item.match_type} />
          {item.text_similarity !== null && (
            <Text size="xs" c="dimmed">
              text similarity {item.text_similarity.toFixed(2)} · {item.matched_passages} matched passages
            </Text>
          )}
        </Group>
        <CaseFacts summary={item.case} />
        <Grid gap="md">
          <Grid.Col span={{ base: 12, md: 6 }}>
            <Text size="sm" fw={500} mb={4}>
              Why it is similar
            </Text>
            <List size="sm" spacing={2}>
              {item.reasons.map((reason) => (
                <List.Item key={reason}>{reason}</List.Item>
              ))}
            </List>
          </Grid.Col>
          <Grid.Col span={{ base: 12, md: 6 }}>
            <Text size="sm" fw={500} mb={4}>
              Differences
            </Text>
            <List size="sm" spacing={2}>
              {item.differences.map((difference) => (
                <List.Item key={difference}>{difference}</List.Item>
              ))}
            </List>
          </Grid.Col>
        </Grid>
        {item.passage_pairs.length > 0 && (
          <>
            <Divider label="Closest passages, side by side" labelPosition="left" />
            {item.passage_pairs.map((pair, index) => (
              // The same historical passage can be closest to several new-case passages: key by position.
              <Grid key={index} gap="sm">
                <Grid.Col span={{ base: 12, md: 6 }}>
                  <Paper withBorder p="sm" radius="sm" h="100%">
                    <Text size="xs" c="dimmed" mb={4}>
                      {newCaseLabel} · {pageLabel(pair.new_case.page_start, pair.new_case.page_end)}
                    </Text>
                    <Text size="sm">{pair.new_case.text}</Text>
                  </Paper>
                </Grid.Col>
                <Grid.Col span={{ base: 12, md: 6 }}>
                  <Paper withBorder p="sm" radius="sm" h="100%">
                    <Text size="xs" c="dimmed" mb={4}>
                      This case · {pageLabel(pair.similar_case.page_start, pair.similar_case.page_end)} · similarity{' '}
                      {pair.similarity.toFixed(2)}
                    </Text>
                    <Text size="sm">{pair.similar_case.text}</Text>
                  </Paper>
                </Grid.Col>
              </Grid>
            ))}
          </>
        )}
        <Group justify="flex-end">
          <Button
            component={Link}
            to={`/cases/${item.case.display_id}`}
            variant="light"
            size="xs"
            rightSection={<IconArrowRight size={14} />}
          >
            View details
          </Button>
        </Group>
      </Stack>
    </Card>
  )
}

export function SimilarResultsHeader({ title, total }: { title: string; total: number }) {
  return (
    <Group justify="space-between">
      <Title order={2} size="h3">
        {title}
      </Title>
      <Text c="dimmed" size="sm">
        {total} similar {total === 1 ? 'case' : 'cases'} found
      </Text>
    </Group>
  )
}
