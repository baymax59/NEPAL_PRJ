// CDR file import wizard: pick format, timezone, MSISDN rule, then upload.

import { Alert, Button, Group, Modal, NativeSelect, Paper, Progress, Stack, Text } from '@mantine/core'
import { Dropzone, type FileWithPath } from '@mantine/dropzone'
import { IconCheck, IconFileSpreadsheet, IconUpload, IconX } from '@tabler/icons-react'
import { useState } from 'react'
import { kh } from '../../api'
import type { CdrImportBatch } from '../../types'

const MSISDN_RULES = [
  { value: 'np-msisdn.v1', label: 'Nepal (np-msisdn.v1)' },
  { value: 'in-msisdn.v1', label: 'India (in-msisdn.v1)' },
]

const TIMEZONES = [
  { value: 'Asia/Kathmandu', label: 'Asia/Kathmandu (NPT +05:45)' },
  { value: 'Asia/Kolkata', label: 'Asia/Kolkata (IST +05:30)' },
  { value: 'UTC', label: 'UTC' },
]

interface Props {
  caseId: string
  opened: boolean
  onClose: () => void
  onDone: (batch: CdrImportBatch) => void
}

type Step = 'pick' | 'uploading' | 'done' | 'error'

export function CdrImportDialog({ caseId, opened, onClose, onDone }: Props) {
  const [file, setFile] = useState<FileWithPath | null>(null)
  const [msisdnRule, setMsisdnRule] = useState('np-msisdn.v1')
  const [timezone, setTimezone] = useState('Asia/Kathmandu')
  const [step, setStep] = useState<Step>('pick')
  const [result, setResult] = useState<CdrImportBatch | null>(null)
  const [error, setError] = useState<string | null>(null)

  const reset = () => {
    setFile(null)
    setStep('pick')
    setResult(null)
    setError(null)
  }

  const handleClose = () => {
    reset()
    onClose()
  }

  const upload = async () => {
    if (!file) return
    setStep('uploading')
    setError(null)
    try {
      const batch = await kh.cdrUpload(caseId, file, msisdnRule, timezone)
      setResult(batch)
      setStep('done')
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      setError(msg)
      setStep('error')
    }
  }

  return (
    <Modal opened={opened} onClose={handleClose} title="Import CDR File" size="md">
      <Stack gap="md">
        {step === 'pick' && (
          <>
            <Dropzone
              onDrop={(files) => setFile(files[0])}
              accept={['text/csv', 'application/vnd.ms-excel', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet']}
              maxSize={50 * 1024 * 1024}
              maxFiles={1}
            >
              <Group justify="center" gap="xl" mih={120} style={{ pointerEvents: 'none' }}>
                <Dropzone.Accept>
                  <IconCheck size={40} stroke={1.5} />
                </Dropzone.Accept>
                <Dropzone.Reject>
                  <IconX size={40} stroke={1.5} />
                </Dropzone.Reject>
                <Dropzone.Idle>
                  <IconFileSpreadsheet size={40} stroke={1.5} />
                </Dropzone.Idle>
                <Stack gap={6} ta="center">
                  <Text size="sm" fw={500}>Drop a CDR file here or click to browse</Text>
                  <Text size="xs" c="dimmed">CSV, XLS or XLSX · max 50 MB</Text>
                </Stack>
              </Group>
            </Dropzone>

            {file && (
              <Paper withBorder p="xs" radius="sm">
                <Group gap="xs">
                  <IconUpload size={16} />
                  <Text size="sm" style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{file.name}</Text>
                  <Text size="xs" c="dimmed">{(file.size / 1024).toFixed(0)} KB</Text>
                  <Button size="compact-xs" variant="subtle" color="gray" onClick={() => setFile(null)}>Remove</Button>
                </Group>
              </Paper>
            )}

            <NativeSelect
              label="MSISDN normalization rule"
              description="Choose the country rule that matches the numbers in this file."
              value={msisdnRule}
              onChange={(e) => setMsisdnRule(e.currentTarget.value)}
              data={MSISDN_RULES}
            />

            <NativeSelect
              label="Source timezone"
              description="The timezone the timestamps in the file are recorded in."
              value={timezone}
              onChange={(e) => setTimezone(e.currentTarget.value)}
              data={TIMEZONES}
            />

            <Group justify="flex-end" gap="xs">
              <Button variant="default" onClick={handleClose}>Cancel</Button>
              <Button disabled={!file} onClick={upload} leftSection={<IconUpload size={14} />}>
                Upload and process
              </Button>
            </Group>
          </>
        )}

        {step === 'uploading' && (
          <Stack gap="md" align="center" py="xl">
            <Text size="sm">Uploading and processing {file?.name}…</Text>
            <Progress w="100%" animated value={100} />
            <Text size="xs" c="dimmed">This may take a moment for large files.</Text>
          </Stack>
        )}

        {step === 'done' && result && (
          <>
            <Alert color="green" icon={<IconCheck size={16} />} title="Import complete">
              <Text size="sm">
                {result.total_rows} rows processed: {result.accepted_rows} accepted,{' '}
                {result.duplicate_rows} duplicates, {result.rejected_rows} rejected.
              </Text>
            </Alert>
            <Group justify="flex-end">
              <Button onClick={() => { reset(); onDone(result) }}>Close</Button>
            </Group>
          </>
        )}

        {step === 'error' && (
          <>
            <Alert color="red" icon={<IconX size={16} />} title="Import failed">
              <Text size="sm">{error}</Text>
            </Alert>
            <Group justify="flex-end">
              <Button variant="default" onClick={reset}>Try again</Button>
              <Button variant="default" onClick={handleClose}>Close</Button>
            </Group>
          </>
        )}
      </Stack>
    </Modal>
  )
}
