// Offence sections: those cited in the case's documents and notes, and those cited by the most similar past cases.
// Prompts for the investigator, never a legal assessment.

import { Alert, Anchor, Badge, Group, Stack, Table, Text } from '@mantine/core'
import { IconScale } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router'
import { kh } from '../../api'
import type { CaseDetail } from '../../types'
import { EmptyState, Loaded, Panel } from '../../ui'
import { Notices, SourceLink } from './common'

const CATEGORY: Record<string, { label: string; color: string }> = {
  criminal_law: { label: 'criminal law', color: 'red' },
  procedure_and_evidence: { label: 'procedure / evidence', color: 'gray' },
  constitution: { label: 'constitution', color: 'gray' },
  other_law: { label: 'other law', color: 'blue' },
}

function Category({ value }: { value: string }) {
  const look = CATEGORY[value] ?? { label: value, color: 'gray' }
  return (
    <Badge size="xs" variant="light" color={look.color}>
      {look.label}
    </Badge>
  )
}

export function OffencesView({ detail }: { detail: CaseDetail }) {
  const query = useQuery({ queryKey: ['kh', 'case', detail.id, 'ci', 'offences'], queryFn: () => kh.offences(detail.id) })
  return (
    <Loaded query={query}>
      {(data) => (
        <Stack gap="md">
          <Alert color="yellow" variant="light" icon={<IconScale size={18} />}>
            <Text size="sm">{data.disclaimer}</Text>
          </Alert>
          <Notices notices={data.notices} />
          <Panel title={`Cited in this case (${data.cited_here.length})`} p="0">
            {data.cited_here.length === 0 ? (
              <EmptyState title="No sections found">No statutory provision was found in the documents and notes you may see.</EmptyState>
            ) : (
              <Table verticalSpacing="xs">
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Section</Table.Th>
                    <Table.Th>What it is (for orientation)</Table.Th>
                    <Table.Th>Cited in</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {data.cited_here.map((p) => (
                    <Table.Tr key={p.key}>
                      <Table.Td>
                        <Stack gap={2}>
                          <Text size="sm" fw={600}>
                            {p.label}
                          </Text>
                          <Category value={p.category} />
                        </Stack>
                      </Table.Td>
                      <Table.Td>
                        <Text size="sm" c={p.description ? undefined : 'dimmed'}>
                          {p.description ?? '—'}
                        </Text>
                      </Table.Td>
                      <Table.Td>
                        <Group gap={6} wrap="wrap">
                          {p.cited_in.map((c) => (
                            <SourceLink
                              key={c.display_id}
                              caseId={detail.id}
                              source={c}
                              pages={c.pages.length ? `p.${c.pages.slice(0, 4).join(', ')}` : undefined}
                            />
                          ))}
                        </Group>
                        <Text size="xs" c="dimmed">
                          {p.mentions} mention{p.mentions === 1 ? '' : 's'}
                        </Text>
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            )}
          </Panel>
          <Panel
            title={`Cited by similar past cases (${data.from_similar_cases.length}; ${data.similar_cases_considered} past case${data.similar_cases_considered === 1 ? '' : 's'} compared)`}
            p="0"
          >
            {data.from_similar_cases.length === 0 ? (
              <EmptyState title="No further sections">The most similar past cases cite no section that this case doesn't already cite.</EmptyState>
            ) : (
              <Table verticalSpacing="xs">
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Section</Table.Th>
                    <Table.Th>What it is (for orientation)</Table.Th>
                    <Table.Th>Cited by</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {data.from_similar_cases.map((s) => (
                    <Table.Tr key={s.key}>
                      <Table.Td>
                        <Stack gap={2}>
                          <Text size="sm" fw={600}>
                            {s.label}
                          </Text>
                          <Category value={s.category} />
                        </Stack>
                      </Table.Td>
                      <Table.Td>
                        <Text size="sm" c={s.description ? undefined : 'dimmed'}>
                          {s.description ?? '—'}
                        </Text>
                      </Table.Td>
                      <Table.Td>
                        <Text size="xs" mb={2}>
                          {s.count} of the {data.similar_cases_considered} most similar past case{data.similar_cases_considered === 1 ? '' : 's'}
                        </Text>
                        <Group gap={6} wrap="wrap">
                          {s.cases.map((c) => (
                            <Anchor key={c.display_id} component={Link} to={`/cases/${encodeURIComponent(c.display_id)}`} ff="monospace" size="xs">
                              {c.display_id}
                            </Anchor>
                          ))}
                        </Group>
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            )}
          </Panel>
        </Stack>
      )}
    </Loaded>
  )
}
