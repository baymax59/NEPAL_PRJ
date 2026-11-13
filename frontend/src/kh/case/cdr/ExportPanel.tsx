// CDR data export — download as CSV or attach analysis summary to the case folder.

import {
  Alert,
  Button,
  Divider,
  Group,
  Paper,
  Stack,
  Text,
  Title,
} from '@mantine/core'
import { IconDownload, IconFolderPlus, IconCheck } from '@tabler/icons-react'
import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { kh } from '../../api'

interface Props {
  caseId: string
}

export function CdrExportPanel({ caseId }: Props) {
  const [csvBusy, setCsvBusy] = useState(false)
  const [csvError, setCsvError] = useState<string | null>(null)

  const exportToCase = useMutation({
    mutationFn: () => kh.cdrExportToCase(caseId),
  })

  const downloadCsv = async () => {
    setCsvBusy(true)
    setCsvError(null)
    try {
      await kh.cdrExportCsv(caseId)
    } catch (e) {
      setCsvError(e instanceof Error ? e.message : 'Download failed')
    } finally {
      setCsvBusy(false)
    }
  }

  return (
    <Stack gap="md">
      <Stack gap={4}>
        <Title order={5} fw={600}>Export CDR Data</Title>
        <Text size="sm" c="dimmed">
          Download all records as a CSV file, or attach an AI-generated analysis summary
          to this case for investigators and legal review.
        </Text>
      </Stack>

      {/* CSV download */}
      <Paper withBorder p="md" radius="sm">
        <Stack gap="xs">
          <Title order={6}>Download as CSV</Title>
          <Text size="sm" c="dimmed">
            Exports every non-duplicate CDR record (up to 50 000 rows) with all available
            fields. Suitable for import into Excel, SPSS, or other analysis tools.
          </Text>
          {csvError && (
            <Alert color="red" p="xs">
              <Text size="xs">{csvError}</Text>
            </Alert>
          )}
          <Group>
            <Button
              size="sm"
              variant="light"
              leftSection={<IconDownload size={14} />}
              loading={csvBusy}
              onClick={downloadCsv}
            >
              Download cdr-records.csv
            </Button>
          </Group>
        </Stack>
      </Paper>

      <Divider label="or" labelPosition="center" />

      {/* Export to case */}
      <Paper withBorder p="md" radius="sm">
        <Stack gap="xs">
          <Title order={6}>Attach analysis to case</Title>
          <Text size="sm" c="dimmed">
            Generates a structured analysis summary (batch statistics, top contacts, anomaly
            count, peak hours) and saves it as an artifact in the <strong>cdr-analysis</strong> folder
            of this case. The artifact will be visible to all case members with access.
          </Text>

          {exportToCase.isSuccess && exportToCase.data && (
            <Alert color="green" icon={<IconCheck size={16} />} p="xs">
              <Stack gap={2}>
                <Text size="sm" fw={500}>Analysis saved to case</Text>
                <Text size="xs" c="dimmed">
                  Artifact <strong>{exportToCase.data.display_id}</strong> — "{exportToCase.data.title}" added to the
                  cdr-analysis folder.
                </Text>
              </Stack>
            </Alert>
          )}

          {exportToCase.isError && (
            <Alert color="red" p="xs">
              <Text size="xs">
                {exportToCase.error instanceof Error
                  ? exportToCase.error.message
                  : 'Export failed. Check that you have permission to add files to this case.'}
              </Text>
            </Alert>
          )}

          <Group>
            <Button
              size="sm"
              leftSection={<IconFolderPlus size={14} />}
              loading={exportToCase.isPending}
              onClick={() => exportToCase.mutate()}
              disabled={exportToCase.isSuccess}
            >
              {exportToCase.isSuccess ? 'Analysis saved' : 'Save analysis to case'}
            </Button>
            {exportToCase.isSuccess && (
              <Button
                size="sm"
                variant="subtle"
                onClick={() => exportToCase.reset()}
              >
                Save again
              </Button>
            )}
          </Group>
        </Stack>
      </Paper>
    </Stack>
  )
}
