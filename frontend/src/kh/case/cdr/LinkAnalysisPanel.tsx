// Feature 4: 2-hop network link analysis — seed from number, expand to contacts.

import {
  Badge,
  Box,
  Button,
  Group,
  NumberInput,
  Paper,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
} from '@mantine/core'
import { IconNetwork, IconSearch } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { kh } from '../../api'
import { EmptyState, Loaded } from '../../ui'

interface Props {
  caseId: string
}

export function CdrLinkAnalysisPanel({ caseId }: Props) {
  const [number, setNumber] = useState('')
  const [hops, setHops] = useState<number>(2)
  const [minCalls, setMinCalls] = useState<number>(1)
  const [submitted, setSubmitted] = useState<{ number: string; hops: number; minCalls: number } | null>(null)

  const query = useQuery({
    queryKey: ['kh', 'cdr', caseId, 'link-graph', submitted?.number, submitted?.hops, submitted?.minCalls],
    queryFn: () => kh.cdrLinkGraph(caseId, submitted!.number, submitted!.hops, submitted!.minCalls),
    enabled: !!(submitted?.number && submitted.number.length >= 3),
  })

  const submit = () => {
    if (number.trim().length >= 3)
      setSubmitted({ number: number.trim(), hops, minCalls })
  }

  return (
    <Stack gap="md">
      <Stack gap={4}>
        <Title order={5} fw={600}>Link Analysis</Title>
        <Text size="sm" c="dimmed">
          Expand a seed number to its network of contacts up to N hops. Reveals indirect
          associations and communication clusters.
        </Text>
      </Stack>

      <Group gap="xs" wrap="wrap" align="flex-end">
        <TextInput
          label="Seed number"
          placeholder="MSISDN to start from"
          value={number}
          onChange={(e) => setNumber(e.currentTarget.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') submit() }}
          leftSection={<IconSearch size={14} />}
          style={{ flex: 1, minWidth: 200 }}
          size="sm"
        />
        <NumberInput
          label="Hops"
          value={hops}
          onChange={(v) => setHops(Number(v) || 2)}
          min={1}
          max={3}
          size="sm"
          style={{ width: 90 }}
        />
        <NumberInput
          label="Min calls"
          value={minCalls}
          onChange={(v) => setMinCalls(Number(v) || 1)}
          min={1}
          size="sm"
          style={{ width: 100 }}
        />
        <Button
          size="sm"
          mt={24}
          leftSection={<IconNetwork size={14} />}
          onClick={submit}
          disabled={number.trim().length < 3}
        >
          Analyse
        </Button>
      </Group>

      {!submitted && (
        <EmptyState title="Enter a seed number above">
          Paste any number from the CDR dataset to map its contact network.
        </EmptyState>
      )}

      {submitted && (
        <Loaded query={query}>
          {(data) =>
            data.nodes.length === 0 ? (
              <EmptyState title="No contacts found">
                No connections found for {submitted.number} with the given filters.
              </EmptyState>
            ) : (
              <Stack gap="md">
                <Group gap="xs">
                  <Badge color="hawk">{data.nodes.length} nodes</Badge>
                  <Badge color="gray">{data.edges.length} edges</Badge>
                  <Text size="xs" c="dimmed">— {submitted.hops}-hop expansion from {submitted.number}</Text>
                </Group>

                {/* Node table */}
                <Paper withBorder radius="sm">
                  <Box p="sm"><Title order={6}>Nodes (numbers in network)</Title></Box>
                  <Box style={{ overflowX: 'auto' }}>
                    <Table striped highlightOnHover withColumnBorders>
                      <Table.Thead>
                        <Table.Tr>
                          <Table.Th>Number</Table.Th>
                          <Table.Th>Hop</Table.Th>
                          <Table.Th>Total calls</Table.Th>
                          <Table.Th>Role</Table.Th>
                        </Table.Tr>
                      </Table.Thead>
                      <Table.Tbody>
                        {data.nodes.map((n) => (
                          <Table.Tr key={n.id}>
                            <Table.Td><Text size="xs" ff="monospace">{n.label}</Text></Table.Td>
                            <Table.Td>
                              <Badge
                                size="xs"
                                color={n.hop === 0 ? 'red' : n.hop === 1 ? 'orange' : 'blue'}
                              >
                                {n.hop === 0 ? 'Seed' : `Hop ${n.hop}`}
                              </Badge>
                            </Table.Td>
                            <Table.Td><Text size="xs">{n.call_count ?? '—'}</Text></Table.Td>
                            <Table.Td>
                              {n.hop === 0
                                ? <Badge size="xs" color="red" variant="outline">Subject</Badge>
                                : <Badge size="xs" variant="outline">Contact</Badge>
                              }
                            </Table.Td>
                          </Table.Tr>
                        ))}
                      </Table.Tbody>
                    </Table>
                  </Box>
                </Paper>

                {/* Edge table */}
                <Paper withBorder radius="sm">
                  <Box p="sm"><Title order={6}>Edges (communication links)</Title></Box>
                  <Box style={{ overflowX: 'auto' }}>
                    <Table striped highlightOnHover withColumnBorders>
                      <Table.Thead>
                        <Table.Tr>
                          <Table.Th>From</Table.Th>
                          <Table.Th>To</Table.Th>
                          <Table.Th>Calls</Table.Th>
                          <Table.Th>Total duration</Table.Th>
                        </Table.Tr>
                      </Table.Thead>
                      <Table.Tbody>
                        {data.edges.map((e, i) => {
                          const fromNode = data.nodes.find((n) => n.id === e.source)
                          const toNode = data.nodes.find((n) => n.id === e.target)
                          const dur = e.total_duration_seconds != null
                            ? e.total_duration_seconds < 3600
                              ? `${Math.floor(e.total_duration_seconds / 60)}m ${e.total_duration_seconds % 60}s`
                              : `${Math.floor(e.total_duration_seconds / 3600)}h ${Math.floor((e.total_duration_seconds % 3600) / 60)}m`
                            : '—'
                          return (
                            <Table.Tr key={i}>
                              <Table.Td><Text size="xs" ff="monospace">{fromNode?.label ?? e.source}</Text></Table.Td>
                              <Table.Td><Text size="xs" ff="monospace">{toNode?.label ?? e.target}</Text></Table.Td>
                              <Table.Td><Badge size="xs">{e.call_count}</Badge></Table.Td>
                              <Table.Td><Text size="xs">{dur}</Text></Table.Td>
                            </Table.Tr>
                          )
                        })}
                      </Table.Tbody>
                    </Table>
                  </Box>
                </Paper>
              </Stack>
            )
          }
        </Loaded>
      )}
    </Stack>
  )
}
