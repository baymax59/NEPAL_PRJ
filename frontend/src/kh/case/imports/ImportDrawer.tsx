// One imported finding: where it came from (provenance), its versions, what uses it, and where else its identifiers
// appear (only in cases you can open).

import { Alert, Anchor, Badge, Button, Code, Divider, Drawer, Group, Paper, Stack, Table, Text, Timeline } from '@mantine/core'
import { IconLink, IconShieldLock } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router'
import { kh } from '../../api'
import { ContentView } from '../../content'
import type { CaseDetail, IdentifierDetail, ImportDetail, OtherCase } from '../../types'
import { ClassificationBadge, Copy, Facts, Loaded, PersonName, When } from '../../ui'
import { type LinkTarget, LinkCaseDialog } from '../LinkCaseDialog'
import { itemColor, linkReason, periodText } from './format'

type Linking = { target: LinkTarget; reason: string }

export function ImportDrawer({ detail, artifactId, onClose }: { detail: CaseDetail; artifactId: string; onClose: () => void }) {
  const query = useQuery({
    queryKey: ['kh', 'case', detail.id, 'imports', artifactId],
    queryFn: () => kh.importDetail(detail.id, artifactId),
  })
  const [linking, setLinking] = useState<Linking | null>(null)
  const canLink = detail.can.add_files
  return (
    <Drawer opened onClose={onClose} position="right" size="xl" title={<Text fw={600}>Imported finding</Text>}>
      <Loaded query={query}>
        {(d: ImportDetail) => (
          <Stack gap="md">
            <Stack gap={6}>
              <Group gap={6}>
                <Badge color={itemColor(d.item_type)} variant="light">
                  {d.item_type_label}
                </Badge>
                <Text ff="monospace" c="dimmed" size="sm">
                  {d.display_id}
                </Text>
                {d.status !== 'active' && <Badge color="gray">withdrawn</Badge>}
                {d.fictional && (
                  <Badge color="yellow" variant="light">
                    fictional test data
                  </Badge>
                )}
              </Group>
              <Text fw={700} size="lg">
                {d.title}
              </Text>
              <Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>
                {d.summary}
              </Text>
              {d.withdrawn_reason && (
                <Alert color="gray" variant="light" p="xs">
                  Withdrawn from the case: {d.withdrawn_reason}. It stays in the history.
                </Alert>
              )}
            </Stack>

            <Paper withBorder p="sm" radius="md">
              <Text fw={600} size="sm" mb="xs">
                Where it came from
              </Text>
              <Facts
                items={[
                  ['Source system', <SourceName key="s" source={d.source} />],
                  ['Record in the source', <Code key="r">{d.source_record_id}</Code>],
                  ['Full record kept at', d.payload_ref ? <Code key="p">{d.payload_ref}</Code> : null],
                  ['Legal authority', d.authority_ref ?? "Not required by the source's policy"],
                  ['When it happened', d.observed_at ? periodText(d.observed_at, d.observed_until) : 'Not stated by the source'],
                  ['Added for', <Group key="b" gap={6}><PersonName person={d.imported_by} /><When at={d.imported_at} /></Group>],
                  ['Sent with', d.received_with ? <Code key="k">{d.received_with}…</Code> : 'the built-in fictional test source'],
                ]}
              />
              <Group gap={6} mt="sm">
                <IconShieldLock size={14} />
                <Text size="xs" c="dimmed">
                  Kept exactly as received: it can't be edited. To correct or explain it, add a note that refers to it, or withdraw it (Files). {d.policy_note}
                </Text>
              </Group>
            </Paper>

            {Object.keys(d.details).length > 0 && (
              <Stack gap={4}>
                <Text fw={600} size="sm">
                  The result, as the source sent it
                </Text>
                <ContentView content={d.details} />
              </Stack>
            )}

            <Stack gap="xs">
              <Text fw={600} size="sm">
                Identifiers ({d.identifiers.length})
              </Text>
              {d.identifiers.length === 0 && (
                <Text size="sm" c="dimmed">
                  This finding names no identifier.
                </Text>
              )}
              {d.identifiers.map((i) => (
                <IdentifierRow
                  key={`${i.type}:${i.value}`}
                  identifier={i}
                  canLink={canLink}
                  onLink={(other) =>
                    setLinking({
                      target: { kind: 'case', id: other.case.id, label: other.case.display_id },
                      reason: linkReason(i.label, i.value, [d.display_id, ...i.in_this_case], other.imports.map((x) => x.display_id)),
                    })
                  }
                />
              ))}
            </Stack>

            {d.history.length > 1 && (
              <Stack gap="xs">
                <Divider />
                <Text fw={600} size="sm">
                  Versions: each time the source changed its record
                </Text>
                <Timeline bulletSize={14} lineWidth={2} active={d.history.length}>
                  {d.history.map((v) => (
                    <Timeline.Item key={v.version_number} title={`Version ${v.version_number}${v.current ? ' (shown)' : ''}`}>
                      <Text size="xs" c="dimmed">
                        {v.change_note ?? 'First received'}
                      </Text>
                      <Group gap="xs" mt={4}>
                        <PersonName person={v.imported_by} size="xs" />
                        <When at={v.imported_at} size="xs" />
                      </Group>
                    </Timeline.Item>
                  ))}
                </Timeline>
              </Stack>
            )}

            {d.used_by.length > 0 && (
              <Stack gap={4}>
                <Divider />
                <Text fw={600} size="sm">
                  Notes and analyses based on it
                </Text>
                {d.used_by.map((u) => (
                  <Text key={u.artifact_id} size="sm">
                    <Code>{u.display_id}</Code> {u.title} (version {u.version_number})
                  </Text>
                ))}
              </Stack>
            )}
          </Stack>
        )}
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
    </Drawer>
  )
}

function SourceName({ source }: { source: ImportDetail['source'] }) {
  return (
    <Group gap={6} wrap="wrap">
      <Text size="sm">{source.name}</Text>
      {source.kind_label && (
        <Badge size="xs" variant="outline" color="gray">
          {source.kind_label}
        </Badge>
      )}
      {source.status === 'disabled' && (
        <Badge size="xs" color="gray">
          source now disabled
        </Badge>
      )}
    </Group>
  )
}

function IdentifierRow({ identifier: i, canLink, onLink }: { identifier: IdentifierDetail; canLink: boolean; onLink: (c: OtherCase) => void }) {
  return (
    <Paper withBorder p="xs" radius="md">
      <Group gap={6} wrap="wrap">
        <Badge variant="default" radius="sm" tt="none">
          {i.label}
        </Badge>
        <Code>{i.value}</Code>
        <Copy value={i.value} />
        {i.as_received && i.as_received !== i.value && (
          <Text size="xs" c="dimmed">
            received as "{i.as_received}"
          </Text>
        )}
      </Group>
      {i.in_this_case.length > 0 && (
        <Text size="xs" c="dimmed" mt={4}>
          Also named by {i.in_this_case.join(', ')} in this case.
        </Text>
      )}
      {i.other_cases.length > 0 && (
        <Table mt={6} verticalSpacing={4} fz="sm" withRowBorders={false}>
          <Table.Tbody>
            {i.other_cases.map((c) => (
              <Table.Tr key={c.case.id}>
                <Table.Td>
                  <Anchor component={Link} to={`/kh/case/${c.case.id}`} size="sm" fw={600}>
                    {c.case.display_id}
                  </Anchor>{' '}
                  <ClassificationBadge value={c.case.classification} />
                  <Text size="xs" c="dimmed">
                    {c.case.title}
                  </Text>
                </Table.Td>
                <Table.Td>
                  <Text size="xs">
                    {c.imports.map((x) => `${x.display_id} (${x.item_type_label.toLowerCase()}, ${x.source ?? 'unknown source'})`).join('; ')}
                  </Text>
                </Table.Td>
                <Table.Td ta="right">
                  {c.linked ? (
                    <Badge color="teal" variant="light" size="sm">
                      linked
                    </Badge>
                  ) : canLink ? (
                    <Button size="compact-xs" variant="light" leftSection={<IconLink size={13} />} onClick={() => onLink(c)} aria-label={`Link ${c.case.display_id}`}>
                      Link cases
                    </Button>
                  ) : null}
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
      {i.other_cases.length === 0 && (
        <Text size="xs" c="dimmed" mt={4}>
          Not found in another case you can open.
        </Text>
      )}
    </Paper>
  )
}
