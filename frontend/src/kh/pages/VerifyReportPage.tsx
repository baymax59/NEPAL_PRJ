// Check a report file: is this PDF, byte for byte, a report Knight Hawk generated? The file is only hashed
// on the server and never kept; details are shown only to people who may open the report's case.

import { Alert, Button, FileInput, Group, Paper, Stack, Text } from '@mantine/core'
import { IconCircleCheck, IconFileSearch, IconShieldX } from '@tabler/icons-react'
import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router'
import { kh } from '../api'
import { toastError } from '../feedback'
import type { ReportCheck } from '../types'
import { EntryNumber, Facts, PageHeader, PersonName } from '../ui'
import { formatWhen } from '../time'

export function VerifyReportPage() {
  const [file, setFile] = useState<File | null>(null)
  const check = useMutation({ mutationFn: (f: File) => kh.verifyReportFile(f), onError: (error) => toastError(error, 'Not checked') })
  return (
    <Stack gap="md" maw={820}>
      <PageHeader eyebrow="Reports" title="Check a report file">
        <Text size="sm" c="dimmed">
          Someone gave you a Knight Hawk report, printed from a download or sent by e-mail? Check that it is exactly the file Knight Hawk generated.
          The file is only compared with the recorded reports of your organisation; it is not kept.
        </Text>
      </PageHeader>
      <Paper withBorder p="md" radius="md">
        <Group align="flex-end" gap="sm">
          <FileInput label="Report file (PDF)" placeholder="Choose the PDF" accept="application/pdf" value={file} onChange={setFile} style={{ flex: 1 }} clearable />
          <Button leftSection={<IconFileSearch size={16} />} disabled={!file} loading={check.isPending} onClick={() => file && check.mutate(file)}>
            Check
          </Button>
        </Group>
      </Paper>
      {check.data && <Result check={check.data} />}
    </Stack>
  )
}

function Result({ check }: { check: ReportCheck }) {
  const genuine = check.result === 'match'
  return (
    <Alert
      color={genuine ? 'teal' : 'red'}
      variant="light"
      icon={genuine ? <IconCircleCheck size={20} /> : <IconShieldX size={20} />}
      title={genuine ? 'Genuine: exactly the report Knight Hawk generated' : 'Not recognised'}
    >
      <Stack gap="sm">
        <Text size="sm">{check.message}</Text>
        {check.report && (
          <Facts
            items={[
              ['Report', `${check.report.display_id}, version ${check.report.version_number}: ${check.report.title}`],
              ['Purpose', check.report.purpose],
              ['Generated', <Group key="g" gap={6}><PersonName person={check.report.generated_by} size="xs" /><Text size="xs">{formatWhen(check.report.generated_at)}</Text></Group>],
              ['Describes', <span key="c">the case as of <EntryNumber seq={check.report.as_of_entry} caseId={check.report.case_id} /></span>],
              ['Open it', <Link key="l" to={`/kh/case/${check.report.case_id}/reports`}>the case's reports</Link>],
            ]}
          />
        )}
        <Text size="xs" c="dimmed">
          A genuine report shows what the case held at one entry of its history. It is not automatically admissible in court.
        </Text>
      </Stack>
    </Alert>
  )
}
