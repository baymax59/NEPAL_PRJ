// CDR Analysis tab: upload CDR files, view records, analytics, link analysis, AI search, and export.

import {
  Badge,
  Button,
  Group,
  Paper,
  Stack,
  Tabs,
  Text,
  Title,
} from '@mantine/core'
import {
  IconAlertTriangle,
  IconDeviceAnalytics,
  IconDeviceMobile,
  IconDownload,
  IconNetwork,
  IconPhone,
  IconPlus,
  IconRobot,
  IconTable,
  IconTimeline,
  IconUsers,
} from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { kh } from '../api'
import { EmptyState, Loaded } from '../ui'
import { useCase } from './context'
import { CdrAnalyticsPanel } from './cdr/AnalyticsPanel'
import { CdrAnomalyPanel } from './cdr/AnomalyPanel'
import { CdrCallGraphPanel } from './cdr/CallGraph'
import { CdrCommonContactsPanel } from './cdr/CommonContactsPanel'
import { CdrExportPanel } from './cdr/ExportPanel'
import { CdrImeiPanel } from './cdr/ImeiPanel'
import { CdrImportDialog } from './cdr/ImportDialog'
import { CdrLinkAnalysisPanel } from './cdr/LinkAnalysisPanel'
import { CdrLlmSearchPanel } from './cdr/LlmSearchPanel'
import { CdrRecordsTable } from './cdr/RecordsTable'
import { CdrTimelinePanel } from './cdr/TimelinePanel'

export function CdrTab() {
  const detail = useCase()
  const [importing, setImporting] = useState(false)

  const batchQuery = useQuery({
    queryKey: ['kh', 'case', detail.id, 'cdr', 'batches'],
    queryFn: () => kh.cdrBatches(detail.id),
  })

  const summaryQuery = useQuery({
    queryKey: ['kh', 'case', detail.id, 'cdr', 'summary'],
    queryFn: () => kh.cdrSummary(detail.id),
  })

  const batches = batchQuery.data ?? []
  const summary = summaryQuery.data

  return (
    <Stack gap="md">
      <Group justify="space-between" wrap="wrap" gap="xs">
        <Stack gap={4}>
          <Group gap="xs">
            <IconPhone size={18} />
            <Title order={3} size="h4" fw={600}>
              CDR Analysis
            </Title>
            {summary && summary.total_records > 0 && (
              <Badge variant="light" color="hawk">{summary.total_records.toLocaleString()} records</Badge>
            )}
          </Group>
          <Text size="sm" c="dimmed">
            Upload and analyse Call Detail Records linked to this case.
          </Text>
        </Stack>
        <Button
          size="xs"
          leftSection={<IconPlus size={14} />}
          onClick={() => setImporting(true)}
        >
          Import CDR file
        </Button>
      </Group>

      {importing && (
        <CdrImportDialog
          caseId={detail.id}
          opened
          onClose={() => setImporting(false)}
          onDone={() => {
            setImporting(false)
            batchQuery.refetch()
            summaryQuery.refetch()
          }}
        />
      )}

      {/* Batch status bar */}
      <Loaded query={batchQuery}>
        {() =>
          batches.length > 0 ? (
            <BatchStatusBar batches={batches} />
          ) : (
            <EmptyState title="No CDR files yet">
              Import a CSV or Excel CDR file to start analysing call records for this case.
            </EmptyState>
          )
        }
      </Loaded>

      {batches.length > 0 && (
        <Tabs defaultValue="records" keepMounted={false}>
          <Tabs.List>
            <Tabs.Tab value="records" leftSection={<IconTable size={14} />}>Records</Tabs.Tab>
            <Tabs.Tab value="analytics" leftSection={<IconDeviceAnalytics size={14} />}>Analytics</Tabs.Tab>
            <Tabs.Tab value="callgraph" leftSection={<IconTimeline size={14} />}>Call Graph</Tabs.Tab>
            <Tabs.Tab value="timeline" leftSection={<IconTimeline size={14} />}>Timeline</Tabs.Tab>
            <Tabs.Tab value="link" leftSection={<IconNetwork size={14} />}>Link Analysis</Tabs.Tab>
            <Tabs.Tab value="contacts" leftSection={<IconUsers size={14} />}>Common Contacts</Tabs.Tab>
            <Tabs.Tab value="imei" leftSection={<IconDeviceMobile size={14} />}>Multi-IMEI</Tabs.Tab>
            <Tabs.Tab value="anomalies" leftSection={<IconAlertTriangle size={14} />}>Anomalies</Tabs.Tab>
            <Tabs.Tab value="ai" leftSection={<IconRobot size={14} />}>AI Search</Tabs.Tab>
            <Tabs.Tab value="export" leftSection={<IconDownload size={14} />}>Export</Tabs.Tab>
          </Tabs.List>

          <Tabs.Panel value="records" pt="md">
            <CdrRecordsTable caseId={detail.id} />
          </Tabs.Panel>

          <Tabs.Panel value="analytics" pt="md">
            <CdrAnalyticsPanel caseId={detail.id} />
          </Tabs.Panel>

          <Tabs.Panel value="callgraph" pt="md">
            <CdrCallGraphPanel caseId={detail.id} />
          </Tabs.Panel>

          <Tabs.Panel value="timeline" pt="md">
            <CdrTimelinePanel caseId={detail.id} />
          </Tabs.Panel>

          <Tabs.Panel value="link" pt="md">
            <CdrLinkAnalysisPanel caseId={detail.id} />
          </Tabs.Panel>

          <Tabs.Panel value="contacts" pt="md">
            <CdrCommonContactsPanel caseId={detail.id} />
          </Tabs.Panel>

          <Tabs.Panel value="imei" pt="md">
            <CdrImeiPanel caseId={detail.id} />
          </Tabs.Panel>

          <Tabs.Panel value="anomalies" pt="md">
            <CdrAnomalyPanel caseId={detail.id} />
          </Tabs.Panel>

          <Tabs.Panel value="ai" pt="md">
            <CdrLlmSearchPanel caseId={detail.id} />
          </Tabs.Panel>

          <Tabs.Panel value="export" pt="md">
            <CdrExportPanel caseId={detail.id} />
          </Tabs.Panel>
        </Tabs>
      )}
    </Stack>
  )
}

function BatchStatusBar({ batches }: { batches: import('../types').CdrImportBatch[] }) {
  const latest = batches[0]
  if (!latest) return null
  const color =
    latest.status === 'completed' ? 'green'
      : latest.status === 'completed_with_errors' ? 'yellow'
        : latest.status === 'failed' ? 'red'
          : latest.status === 'processing' ? 'blue'
            : 'gray'
  return (
    <Paper withBorder p="xs" radius="sm">
      <Group gap="xs" wrap="wrap">
        <Text size="sm" fw={500}>Latest import:</Text>
        <Text size="sm">{latest.file_name}</Text>
        <Badge color={color} size="sm">{latest.status.replace(/_/g, ' ')}</Badge>
        {latest.total_rows != null && (
          <Text size="sm" c="dimmed">
            {latest.accepted_rows} accepted · {latest.duplicate_rows} duplicates · {latest.rejected_rows} rejected
          </Text>
        )}
        <Text size="sm" c="dimmed">({batches.length} batch{batches.length !== 1 ? 'es' : ''} total)</Text>
      </Group>
    </Paper>
  )
}
