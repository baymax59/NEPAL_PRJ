// Feature 10: Multi-number / Multi-IMEI analysis.

import { Badge, Box, Paper, SimpleGrid, Stack, Table, Text, Title } from '@mantine/core'
import { IconAlertTriangle } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { kh } from '../../api'
import { EmptyState, Loaded } from '../../ui'

interface Props {
  caseId: string
}

export function CdrImeiPanel({ caseId }: Props) {
  const query = useQuery({
    queryKey: ['kh', 'cdr', caseId, 'imei-associations'],
    queryFn: () => kh.cdrImeiAssociations(caseId),
  })

  return (
    <Stack gap="md">
      <Stack gap={4}>
        <Title order={5} fw={600}>Multi-Number / Multi-IMEI Analysis</Title>
        <Text size="sm" c="dimmed">
          Correlate phone numbers with devices. A single IMEI used by multiple numbers,
          or a number seen across multiple devices, may indicate SIM swapping or device sharing.
        </Text>
      </Stack>

      <Loaded query={query}>
        {(data) =>
          data.total_imeis === 0 ? (
            <EmptyState title="No IMEI data">
              Imported CDR records do not contain IMEI information.
            </EmptyState>
          ) : (
            <Stack gap="md">
              <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="sm">
                <Paper withBorder p="sm" radius="sm" ta="center">
                  <Text size="xs" c="dimmed" tt="uppercase" fw={600}>Total IMEIs</Text>
                  <Text size="lg" fw={700}>{data.total_imeis}</Text>
                </Paper>
                <Paper withBorder p="sm" radius="sm" ta="center">
                  <Text size="xs" c="dimmed" tt="uppercase" fw={600}>Flagged IMEIs</Text>
                  <Text size="lg" fw={700} c={data.flagged_imeis > 0 ? 'red' : undefined}>
                    {data.flagged_imeis}
                  </Text>
                </Paper>
                <Paper withBorder p="sm" radius="sm" ta="center">
                  <Text size="xs" c="dimmed" tt="uppercase" fw={600}>Multi-IMEI Numbers</Text>
                  <Text size="lg" fw={700} c={data.multi_imei_numbers.length > 0 ? 'orange' : undefined}>
                    {data.multi_imei_numbers.length}
                  </Text>
                </Paper>
              </SimpleGrid>

              {data.flagged_imeis > 0 && (
                <Paper withBorder p="sm" radius="sm" style={{ borderColor: 'var(--mantine-color-red-4)' }}>
                  <Text size="sm" fw={500} c="red">
                    <IconAlertTriangle size={14} style={{ verticalAlign: 'middle' }} /> {data.flagged_imeis} device(s) used by multiple numbers — requires investigation.
                  </Text>
                </Paper>
              )}

              <Paper withBorder radius="sm">
                <Box p="sm"><Title order={6}>IMEI — Number Associations</Title></Box>
                <Box style={{ overflowX: 'auto' }}>
                  <Table striped highlightOnHover withColumnBorders>
                    <Table.Thead>
                      <Table.Tr>
                        <Table.Th>IMEI</Table.Th>
                        <Table.Th>Numbers</Table.Th>
                        <Table.Th>First Seen</Table.Th>
                        <Table.Th>Last Seen</Table.Th>
                        <Table.Th>Flag</Table.Th>
                      </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                      {data.imei_table.map((row) => (
                        <Table.Tr key={row.imei}>
                          <Table.Td><Text size="xs" ff="monospace">{row.imei}</Text></Table.Td>
                          <Table.Td>
                            <Stack gap={2}>
                              {row.numbers.map((n) => (
                                <Text key={n} size="xs" ff="monospace">{n}</Text>
                              ))}
                            </Stack>
                          </Table.Td>
                          <Table.Td>
                            <Text size="xs">{row.first_seen ? new Date(row.first_seen).toLocaleDateString() : '—'}</Text>
                          </Table.Td>
                          <Table.Td>
                            <Text size="xs">{row.last_seen ? new Date(row.last_seen).toLocaleDateString() : '—'}</Text>
                          </Table.Td>
                          <Table.Td>
                            {row.flagged ? (
                              <Badge color="red" size="xs">Multi-number</Badge>
                            ) : (
                              <Badge color="green" size="xs" variant="outline">Normal</Badge>
                            )}
                          </Table.Td>
                        </Table.Tr>
                      ))}
                    </Table.Tbody>
                  </Table>
                </Box>
              </Paper>

              {data.multi_imei_numbers.length > 0 && (
                <Paper withBorder radius="sm">
                  <Box p="sm"><Title order={6}>Numbers Seen on Multiple Devices</Title></Box>
                  <Box style={{ overflowX: 'auto' }}>
                    <Table striped highlightOnHover withColumnBorders>
                      <Table.Thead>
                        <Table.Tr>
                          <Table.Th>Number</Table.Th>
                          <Table.Th>Device count</Table.Th>
                          <Table.Th>IMEIs</Table.Th>
                        </Table.Tr>
                      </Table.Thead>
                      <Table.Tbody>
                        {data.multi_imei_numbers.map((row) => (
                          <Table.Tr key={row.number}>
                            <Table.Td><Text size="xs" ff="monospace">{row.number}</Text></Table.Td>
                            <Table.Td>
                              <Badge color="orange">{row.imei_count}</Badge>
                            </Table.Td>
                            <Table.Td>
                              <Stack gap={2}>
                                {row.imeis.map((im) => (
                                  <Text key={im} size="xs" ff="monospace">{im}</Text>
                                ))}
                              </Stack>
                            </Table.Td>
                          </Table.Tr>
                        ))}
                      </Table.Tbody>
                    </Table>
                  </Box>
                </Paper>
              )}
            </Stack>
          )
        }
      </Loaded>
    </Stack>
  )
}
