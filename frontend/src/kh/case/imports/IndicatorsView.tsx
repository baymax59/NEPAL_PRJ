// Every identifier the case's imported findings name (IP addresses, domains, phone numbers, IMEI, IMSI…), and the other
// cases where it appears: only cases you can open, and only findings you may see there.

import { Anchor, Badge, Button, Code, Group, SimpleGrid, Stack, Table, Text } from '@mantine/core'
import { IconFingerprint, IconLink } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router'
import { kh } from '../../api'
import type { CaseDetail, IndicatorRow, IndicatorsView as IndicatorsData } from '../../types'
import { Copy, EmptyState, Loaded, Stat } from '../../ui'
import { type LinkTarget, LinkCaseDialog } from '../LinkCaseDialog'
import { linkReason } from './format'

export function IndicatorsView({ detail, onOpen }: { detail: CaseDetail; onOpen: (artifactId: string) => void }) {
  const query = useQuery({ queryKey: ['kh', 'case', detail.id, 'imports', 'indicators'], queryFn: () => kh.indicators(detail.id) })
  const [linking, setLinking] = useState<{ target: LinkTarget; reason: string } | null>(null)
  const canLink = detail.can.add_files
  return (
    <>
      <Loaded query={query}>
        {(data: IndicatorsData) =>
          data.indicators.length === 0 ? (
            <EmptyState title="No identifiers yet" icon={<IconFingerprint size={22} />}>
              Identifiers named by imported findings (IP addresses, domains, phone numbers, IMEI, IMSI, accounts…) are listed here, with the other
              cases where they appear.
            </EmptyState>
          ) : (
            <Stack gap="sm">
              <SimpleGrid cols={{ base: 1, sm: 3 }}>
                <Stat label="Identifiers" value={data.totals.identifiers} />
                <Stat label="Also in other cases" value={data.totals.with_matches} color={data.totals.with_matches ? 'orange' : undefined} />
                <Stat label="Other cases involved" value={data.totals.cases} />
              </SimpleGrid>
              <Text size="xs" c="dimmed">
                {data.note} A shared identifier is a lead to check, not proof that two cases are connected.
              </Text>
              <Table.ScrollContainer minWidth={640}>
                <Table verticalSpacing="xs" highlightOnHover>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Identifier</Table.Th>
                      <Table.Th>In this case</Table.Th>
                      <Table.Th>In other cases</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {data.indicators.map((row) => (
                      <Row
                        key={`${row.type}:${row.value}`}
                        row={row}
                        canLink={canLink}
                        onOpen={onOpen}
                        onLink={(c) =>
                          setLinking({
                            target: { kind: 'case', id: c.case.id, label: c.case.display_id },
                            reason: linkReason(row.label, row.value, row.imports.map((i) => i.display_id), c.imports.map((i) => i.display_id)),
                          })
                        }
                      />
                    ))}
                  </Table.Tbody>
                </Table>
              </Table.ScrollContainer>
            </Stack>
          )
        }
      </Loaded>
      {linking && (
        <LinkCaseDialog
          detail={detail}
          target={linking.target}
          initialType="shared_evidence"
          initialReason={linking.reason}
          hint="A shared identifier is a lead, not proof that the cases are connected: check it, and say what connects them."
          onClose={() => setLinking(null)}
        />
      )}
    </>
  )
}

function Row({ row, canLink, onOpen, onLink }: { row: IndicatorRow; canLink: boolean; onOpen: (id: string) => void; onLink: (c: IndicatorRow['other_cases'][number]) => void }) {
  return (
    <Table.Tr>
      <Table.Td>
        <Text size="xs" c="dimmed">
          {row.label}
        </Text>
        <Group gap={4} wrap="nowrap">
          <Code>{row.value}</Code>
          <Copy value={row.value} />
        </Group>
      </Table.Td>
      <Table.Td>
        <Group gap={4}>
          {row.imports.map((i) => (
            <Badge
              key={i.artifact_id}
              variant="light"
              color={i.status === 'active' ? 'hawk' : 'gray'}
              size="sm"
              style={{ cursor: 'pointer' }}
              onClick={() => onOpen(i.artifact_id)}
              title={`${i.item_type_label}${i.status === 'active' ? '' : ' (withdrawn)'}`}
            >
              {i.display_id}
            </Badge>
          ))}
        </Group>
      </Table.Td>
      <Table.Td>
        {row.other_cases.length === 0 ? (
          <Text size="xs" c="dimmed">
            None that you can open
          </Text>
        ) : (
          <Stack gap={4}>
            {row.other_cases.map((c) => (
              <Group key={c.case.id} gap={6} wrap="wrap">
                <Anchor component={Link} to={`/kh/case/${c.case.id}`} size="sm" fw={600}>
                  {c.case.display_id}
                </Anchor>
                <Text size="xs" c="dimmed" lineClamp={1} maw={260}>
                  {c.case.title}
                </Text>
                <Text size="xs">{c.imports.map((i) => i.display_id).join(', ')}</Text>
                {c.linked ? (
                  <Badge color="teal" variant="light" size="xs">
                    linked
                  </Badge>
                ) : canLink ? (
                  <Button size="compact-xs" variant="light" leftSection={<IconLink size={12} />} onClick={() => onLink(c)} aria-label={`Link ${c.case.display_id}`}>
                    Link
                  </Button>
                ) : null}
              </Group>
            ))}
          </Stack>
        )}
      </Table.Td>
    </Table.Tr>
  )
}
