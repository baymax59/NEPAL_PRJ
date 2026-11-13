// Similar cases for this investigation: other investigations you may open, and past cases of the knowledge base.
// Each says why it was found and how it differs, and can be linked (with a reason).

import { Accordion, Anchor, Badge, Button, Group, List, Paper, SimpleGrid, Stack, Text } from '@mantine/core'
import { IconCheck, IconLink } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router'
import { kh } from '../../api'
import type { CaseDetail, KnowledgeMatch, SimilarInvestigation } from '../../types'
import { ClassificationBadge, EmptyState, Loaded, Panel, WorkflowBadge } from '../../ui'
import { formatDay } from '../../time'
import { type LinkTarget, LinkCaseDialog } from '../LinkCaseDialog'
import { Notices, Relevance } from './common'
import { pageText } from './format'

const MATCH: Record<string, string> = {
  text: 'Similar text',
  provisions: 'Same provisions',
  same_file: 'Same file',
  'text+provisions': 'Similar text + same provisions',
}

type Pair = { similarity: number; mine: { source?: string | null; text: string }; theirs: { label: string; text: string } }

function Pairs({ pairs, theirLabel }: { pairs: Pair[]; theirLabel: string }) {
  if (!pairs.length) return null
  return (
    <Accordion variant="contained" chevronPosition="left" mt={6}>
      <Accordion.Item value="pairs">
        <Accordion.Control>
          <Text size="xs">Closest passages ({pairs.length})</Text>
        </Accordion.Control>
        <Accordion.Panel>
          <Stack gap="xs">
            {pairs.map((p, i) => (
              <SimpleGrid key={i} cols={{ base: 1, md: 2 }} spacing="xs">
                <Paper withBorder p="xs" radius="sm">
                  <Group gap={6} mb={2}>
                    <Text size="10px" tt="uppercase" fw={600} c="dimmed">
                      This investigation
                    </Text>
                    <Text size="xs" ff="monospace">
                      {p.mine.source}
                    </Text>
                  </Group>
                  <Text size="xs">{p.mine.text}</Text>
                </Paper>
                <Paper withBorder p="xs" radius="sm">
                  <Group gap={6} mb={2} justify="space-between">
                    <Group gap={6}>
                      <Text size="10px" tt="uppercase" fw={600} c="dimmed">
                        {theirLabel}
                      </Text>
                      <Text size="xs" ff="monospace">
                        {p.theirs.label}
                      </Text>
                    </Group>
                    <Badge size="xs" variant="light" color="gray">
                      similarity {p.similarity.toFixed(2)}
                    </Badge>
                  </Group>
                  <Text size="xs">{p.theirs.text}</Text>
                </Paper>
              </SimpleGrid>
            ))}
          </Stack>
        </Accordion.Panel>
      </Accordion.Item>
    </Accordion>
  )
}

function Reasons({ reasons, differences }: { reasons: string[]; differences: string[] }) {
  return (
    <Stack gap={4} mt={6}>
      <List size="sm" spacing={2}>
        {reasons.map((r) => (
          <List.Item key={r}>{r}</List.Item>
        ))}
      </List>
      {differences.length > 0 && (
        <Text size="xs" c="dimmed">
          {differences.join(' · ')}
        </Text>
      )}
    </Stack>
  )
}

function LinkAction({ linked, canLink, onLink }: { linked: boolean; canLink: boolean; onLink: () => void }) {
  if (linked)
    return (
      <Badge color="teal" variant="light" leftSection={<IconCheck size={11} />}>
        Linked
      </Badge>
    )
  if (!canLink) return null
  return (
    <Button size="compact-xs" variant="light" leftSection={<IconLink size={12} />} onClick={onLink}>
      Link
    </Button>
  )
}

function InvestigationCard({ result, canLink, onLink }: { result: SimilarInvestigation; canLink: boolean; onLink: () => void }) {
  return (
    <Paper withBorder p="sm" radius="sm">
      <Group justify="space-between" align="flex-start" wrap="nowrap" gap="sm">
        <Stack gap={2} style={{ minWidth: 0 }}>
          <Group gap={6}>
            <Anchor component={Link} to={`/kh/case/${result.case.id}`} ff="monospace" fw={700} size="sm">
              {result.case.display_id}
            </Anchor>
            <WorkflowBadge value={result.case.workflow_status} />
            <ClassificationBadge value={result.case.classification} />
          </Group>
          <Text size="sm" fw={500}>
            {result.case.title}
          </Text>
        </Stack>
        <Stack gap={6} align="flex-end">
          <Relevance value={result.relevance} />
          <LinkAction linked={result.linked} canLink={canLink} onLink={onLink} />
        </Stack>
      </Group>
      <Group gap={4} mt={6}>
        {result.match_type.map((m) => (
          <Badge key={m} size="xs" variant="light" color={m === 'same_file' ? 'grape' : 'hawk'}>
            {MATCH[m] ?? m}
          </Badge>
        ))}
      </Group>
      <Reasons reasons={result.reasons} differences={result.differences} />
      <Pairs
        theirLabel={result.case.display_id}
        pairs={result.passage_pairs.map((p) => ({ similarity: p.similarity, mine: p.this_case, theirs: { label: p.other_case.source ?? '', text: p.other_case.text } }))}
      />
    </Paper>
  )
}

function KnowledgeCard({ result, canLink, onLink }: { result: KnowledgeMatch; canLink: boolean; onLink: () => void }) {
  const c = result.case
  return (
    <Paper withBorder p="sm" radius="sm">
      <Group justify="space-between" align="flex-start" wrap="nowrap" gap="sm">
        <Stack gap={2} style={{ minWidth: 0 }}>
          <Group gap={6}>
            <Anchor component={Link} to={`/cases/${encodeURIComponent(c.display_id)}`} ff="monospace" fw={700} size="sm">
              {c.display_id}
            </Anchor>
            <Badge size="xs" variant="outline" color="gray">
              past case
            </Badge>
          </Group>
          <Text size="sm" fw={500}>
            {c.title ?? 'Untitled'}
          </Text>
          <Text size="xs" c="dimmed">
            {[c.court_or_agency, c.primary_date ? `decided ${formatDay(c.primary_date)}` : null, c.outcome ? `outcome: ${c.outcome}` : 'no outcome recorded']
              .filter(Boolean)
              .join(' · ')}
          </Text>
        </Stack>
        <Stack gap={6} align="flex-end">
          <Relevance value={result.relevance} />
          <LinkAction linked={result.linked} canLink={canLink} onLink={onLink} />
        </Stack>
      </Group>
      <Group gap={4} mt={6}>
        <Badge size="xs" variant="light" color="hawk">
          {MATCH[result.match_type] ?? result.match_type}
        </Badge>
        {result.shared_provisions.slice(0, 4).map((p) => (
          <Badge key={p} size="xs" variant="outline" color="gray">
            {p}
          </Badge>
        ))}
      </Group>
      <Reasons reasons={result.reasons} differences={result.differences} />
      <Pairs
        theirLabel="Past case"
        pairs={result.passage_pairs.map((p) => ({
          similarity: p.similarity,
          mine: { source: p.new_case.source, text: p.new_case.text },
          theirs: { label: pageText(p.similar_case.page_start, p.similar_case.page_end) || 'passage', text: p.similar_case.text },
        }))}
      />
    </Paper>
  )
}

export function SimilarView({ detail }: { detail: CaseDetail }) {
  const query = useQuery({ queryKey: ['kh', 'case', detail.id, 'ci', 'similar'], queryFn: () => kh.similarCases(detail.id) })
  const [target, setTarget] = useState<LinkTarget | null>(null)
  const canLink = detail.can.add_files
  return (
    <Loaded query={query}>
      {(data) => (
        <Stack gap="md">
          <Notices notices={data.notices} />
          <Panel title={`Other investigations (${data.investigations_total})`}>
            {data.investigations.length === 0 ? (
              <EmptyState title="No similar investigation found">Only investigations you may open are compared.</EmptyState>
            ) : (
              <Stack gap="sm">
                {data.investigations.map((r) => (
                  <InvestigationCard key={r.case.id} result={r} canLink={canLink} onLink={() => setTarget({ kind: 'case', id: r.case.id, label: r.case.display_id })} />
                ))}
              </Stack>
            )}
          </Panel>
          <Panel title={`Past cases in the knowledge base (${data.knowledge_total})`}>
            {data.knowledge_base.length === 0 ? (
              <EmptyState title="No similar past case found">Past cases are compared within your clearance and grants.</EmptyState>
            ) : (
              <Stack gap="sm">
                {data.knowledge_base.map((r) => (
                  <KnowledgeCard key={r.case.display_id} result={r} canLink={canLink} onLink={() => setTarget({ kind: 'knowledge', id: r.case.display_id, label: r.case.display_id })} />
                ))}
              </Stack>
            )}
          </Panel>
          <Text size="xs" c="dimmed">
            {data.method_note} Compared: {data.query.passages_used} of {data.query.passages_total} passages
            {data.query.provisions.length ? `; provisions found: ${data.query.provisions.slice(0, 8).join(', ')}` : ''}.
          </Text>
          {target && <LinkCaseDialog detail={detail} target={target} onClose={() => setTarget(null)} />}
        </Stack>
      )}
    </Loaded>
  )
}
