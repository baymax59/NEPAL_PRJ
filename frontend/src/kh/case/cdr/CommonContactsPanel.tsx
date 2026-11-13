// Feature 6: Common contacts and co-location analysis between two numbers.

import { Badge, Box, Button, Group, Paper, SimpleGrid, Stack, Table, Text, TextInput, Title } from '@mantine/core'
import { IconSearch } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { kh } from '../../api'
import { EmptyState, Loaded } from '../../ui'

interface Props {
  caseId: string
}

export function CdrCommonContactsPanel({ caseId }: Props) {
  const [a, setA] = useState('')
  const [b, setB] = useState('')
  const [submitted, setSubmitted] = useState<{ a: string; b: string } | null>(null)

  const query = useQuery({
    queryKey: ['kh', 'cdr', caseId, 'common-contacts', submitted?.a, submitted?.b],
    queryFn: () => kh.cdrCommonContacts(caseId, submitted!.a, submitted!.b),
    enabled: !!(submitted?.a && submitted?.b),
  })

  const submit = () => {
    if (a.trim().length >= 3 && b.trim().length >= 3)
      setSubmitted({ a: a.trim(), b: b.trim() })
  }

  return (
    <Stack gap="md">
      <Stack gap={4}>
        <Title order={5} fw={600}>Common Contacts &amp; Co-location</Title>
        <Text size="sm" c="dimmed">
          Find shared contacts and tower events between two subscribers.
        </Text>
      </Stack>

      <Group gap="xs" wrap="wrap" align="flex-end">
        <TextInput
          label="Number A"
          placeholder="First MSISDN"
          value={a}
          onChange={(e) => setA(e.currentTarget.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') submit() }}
          style={{ flex: 1, minWidth: 160 }}
          size="sm"
        />
        <TextInput
          label="Number B"
          placeholder="Second MSISDN"
          value={b}
          onChange={(e) => setB(e.currentTarget.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') submit() }}
          style={{ flex: 1, minWidth: 160 }}
          size="sm"
        />
        <Button
          size="sm"
          mt={24}
          leftSection={<IconSearch size={14} />}
          onClick={submit}
          disabled={a.trim().length < 3 || b.trim().length < 3}
        >
          Compare
        </Button>
      </Group>

      {!submitted && (
        <EmptyState title="Enter two phone numbers above">
          Enter the two MSISDNs you want to compare.
        </EmptyState>
      )}

      {submitted && (
        <Loaded query={query}>
          {(data) => (
            <Stack gap="md">
              <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="sm">
                <Paper withBorder p="sm" radius="sm" ta="center">
                  <Text size="xs" c="dimmed" tt="uppercase" fw={600}>Contacts of A</Text>
                  <Text size="lg" fw={700}>{data.contacts_a_count}</Text>
                </Paper>
                <Paper withBorder p="sm" radius="sm" ta="center">
                  <Text size="xs" c="dimmed" tt="uppercase" fw={600}>Contacts of B</Text>
                  <Text size="lg" fw={700}>{data.contacts_b_count}</Text>
                </Paper>
                <Paper withBorder p="sm" radius="sm" ta="center" style={{ background: 'var(--mantine-color-hawk-0)' }}>
                  <Text size="xs" c="dimmed" tt="uppercase" fw={600}>Shared Contacts</Text>
                  <Text size="lg" fw={700} c="hawk">{data.shared_contact_count}</Text>
                </Paper>
                <Paper withBorder p="sm" radius="sm" ta="center">
                  <Text size="xs" c="dimmed" tt="uppercase" fw={600}>Co-location Events</Text>
                  <Text size="lg" fw={700}>{data.colocation_events.length}</Text>
                </Paper>
              </SimpleGrid>

              {data.shared_contacts.length > 0 && (
                <Paper withBorder p="md" radius="sm">
                  <Title order={6} mb="xs">Shared contacts ({data.shared_contacts.length})</Title>
                  <Group gap={6} wrap="wrap">
                    {data.shared_contacts.map((n) => (
                      <Badge key={n} variant="light" color="hawk" ff="monospace" size="sm">{n}</Badge>
                    ))}
                  </Group>
                </Paper>
              )}

              {data.colocation_events.length > 0 && (
                <Paper withBorder radius="sm">
                  <Box p="sm">
                    <Title order={6}>Co-location events (same cell tower within 1 hour)</Title>
                    <Text size="xs" c="dimmed" mt={2}>
                      A shared tower does not confirm the people were at the same physical location.
                    </Text>
                  </Box>
                  <Box style={{ overflowX: 'auto' }}>
                    <Table striped highlightOnHover withColumnBorders>
                      <Table.Thead>
                        <Table.Tr>
                          <Table.Th>Cell ID</Table.Th>
                          <Table.Th>Time (A)</Table.Th>
                          <Table.Th>Time (B)</Table.Th>
                          <Table.Th>Gap</Table.Th>
                        </Table.Tr>
                      </Table.Thead>
                      <Table.Tbody>
                        {data.colocation_events.map((ev, i) => (
                          <Table.Tr key={i}>
                            <Table.Td><Text size="xs" ff="monospace">{ev.cell_id}</Text></Table.Td>
                            <Table.Td><Text size="xs">{new Date(ev.time_a).toLocaleString()}</Text></Table.Td>
                            <Table.Td><Text size="xs">{new Date(ev.time_b).toLocaleString()}</Text></Table.Td>
                            <Table.Td><Text size="xs">{ev.gap_minutes} min</Text></Table.Td>
                          </Table.Tr>
                        ))}
                      </Table.Tbody>
                    </Table>
                  </Box>
                </Paper>
              )}

              {data.shared_contacts.length === 0 && data.colocation_events.length === 0 && (
                <EmptyState title="No shared contacts or co-location events found">
                  These two numbers have no common contacts or shared cell towers in the dataset.
                </EmptyState>
              )}
            </Stack>
          )}
        </Loaded>
      )}
    </Stack>
  )
}
