// Feature 8: Anomaly detection — bulk SMS, SIM swap, rapid location changes, shared IMEI.

import { Alert, Badge, Box, Group, Paper, Stack, Table, Text, Title } from '@mantine/core'
import { IconCheck, IconShieldCheck } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { kh } from '../../api'
import type { CdrAnomaly } from '../../types'
import { Loaded } from '../../ui'

interface Props {
  caseId: string
}

const TYPE_LABEL: Record<string, string> = {
  bulk_sms: 'Bulk SMS',
  sim_swap: 'SIM Swap',
  rapid_location_change: 'Rapid Location Change',
  shared_imei: 'Shared IMEI',
}

const SEV_COLOR: Record<string, string> = {
  high: 'red',
  medium: 'yellow',
  low: 'blue',
}

function AnomalyRow({ a }: { a: CdrAnomaly }) {
  const color = SEV_COLOR[a.severity] ?? 'gray'
  return (
    <Table.Tr>
      <Table.Td>
        <Badge color={color} size="sm">{a.severity}</Badge>
      </Table.Td>
      <Table.Td>
        <Badge variant="outline" size="sm">{TYPE_LABEL[a.type] ?? a.type}</Badge>
      </Table.Td>
      <Table.Td>
        {a.number && <Text size="xs" ff="monospace">{a.number}</Text>}
        {a.imei && !a.number && <Text size="xs" ff="monospace">IMEI: {a.imei}</Text>}
      </Table.Td>
      <Table.Td>
        <Text size="xs">{a.description}</Text>
      </Table.Td>
      <Table.Td>
        <Text size="xs" c="dimmed" ff="monospace">
          {a.type === 'sim_swap' && a.imeis
            ? a.imeis.join(', ')
            : a.type === 'shared_imei' && a.numbers
              ? a.numbers.join(', ')
              : a.type === 'rapid_location_change'
                ? `${a.cell_from ?? ''} → ${a.cell_to ?? ''}`
                : a.type === 'bulk_sms'
                  ? `${a.event_count ?? ''} events`
                  : ''}
        </Text>
      </Table.Td>
    </Table.Tr>
  )
}

export function CdrAnomalyPanel({ caseId }: Props) {
  const query = useQuery({
    queryKey: ['kh', 'cdr', caseId, 'anomalies'],
    queryFn: () => kh.cdrAnomalies(caseId),
  })

  return (
    <Stack gap="md">
      <Stack gap={4}>
        <Title order={5} fw={600}>Anomaly Detection</Title>
        <Text size="sm" c="dimmed">
          Automatically identified suspicious CDR patterns.
          These are indicators requiring investigator verification, not proof of wrongdoing.
        </Text>
      </Stack>

      <Alert color="blue" icon={<IconShieldCheck size={16} />} p="xs">
        <Text size="xs">
          Detects: bulk SMS activity (&gt;50 messages/hour), SIM swaps (number on multiple devices),
          rapid location changes (different towers within 30 min), and shared IMEIs (possible cloning).
        </Text>
      </Alert>

      <Loaded query={query}>
        {(anomalies) =>
          anomalies.length === 0 ? (
            <Paper withBorder p="lg" radius="sm" ta="center">
              <Group justify="center" gap="xs">
                <IconCheck size={20} color="green" />
                <Text size="sm" c="dimmed">No anomalies detected in the current CDR dataset.</Text>
              </Group>
            </Paper>
          ) : (
            <Stack gap="sm">
              <Group gap="xs">
                {(['high', 'medium', 'low'] as const).map((sev) => {
                  const count = anomalies.filter((a) => a.severity === sev).length
                  return count > 0 ? (
                    <Badge key={sev} color={SEV_COLOR[sev]} size="sm">
                      {count} {sev}
                    </Badge>
                  ) : null
                })}
                <Text size="xs" c="dimmed">— {anomalies.length} total indicators</Text>
              </Group>

              <Paper withBorder radius="sm">
                <Box style={{ overflowX: 'auto' }}>
                  <Table striped highlightOnHover>
                    <Table.Thead>
                      <Table.Tr>
                        <Table.Th>Severity</Table.Th>
                        <Table.Th>Type</Table.Th>
                        <Table.Th>Number / IMEI</Table.Th>
                        <Table.Th>Description</Table.Th>
                        <Table.Th>Details</Table.Th>
                      </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                      {anomalies.map((a, i) => <AnomalyRow key={i} a={a} />)}
                    </Table.Tbody>
                  </Table>
                </Box>
              </Paper>
            </Stack>
          )
        }
      </Loaded>
    </Stack>
  )
}
