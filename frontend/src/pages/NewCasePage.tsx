import { Group, List, Stack, Text, Title } from '@mantine/core'
import { Dropzone, type FileRejection } from '@mantine/dropzone'
import { IconFileText, IconUpload, IconX } from '@tabler/icons-react'
import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate } from 'react-router'
import { uploadCase } from '../api/endpoints'
import { ErrorAlert } from '../components/common'

const MAX_MB = 20
const ACCEPT = {
  'application/pdf': ['.pdf'],
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
  'text/plain': ['.txt'],
}

export function NewCasePage() {
  const navigate = useNavigate()
  const [rejected, setRejected] = useState<string | null>(null)
  const upload = useMutation({
    mutationFn: uploadCase,
    onSuccess: (result) => navigate(`/uploads/${result.id}`),
  })

  function onReject(files: FileRejection[]) {
    const reason = files[0]?.errors[0]
    setRejected(
      reason?.code === 'file-too-large'
        ? `The file is larger than ${MAX_MB} MB.`
        : 'Only PDF, Word (.docx) and plain text (.txt) files can be uploaded.',
    )
  }

  return (
    <Stack gap="md">
      <div>
        <Title order={1} size="h3">
          Find cases similar to a new case
        </Title>
        <Text c="dimmed" size="sm">
          Upload the new case document. Its text is compared with the historical cases you can see.
        </Text>
      </div>
      <Dropzone
        onDrop={(files) => {
          setRejected(null)
          if (files[0]) upload.mutate(files[0])
        }}
        onReject={onReject}
        maxSize={MAX_MB * 1024 * 1024}
        maxFiles={1}
        multiple={false}
        accept={ACCEPT}
        loading={upload.isPending}
      >
        <Group justify="center" gap="xl" mih={180} style={{ pointerEvents: 'none' }}>
          <Dropzone.Accept>
            <IconUpload size={48} stroke={1.5} />
          </Dropzone.Accept>
          <Dropzone.Reject>
            <IconX size={48} stroke={1.5} />
          </Dropzone.Reject>
          <Dropzone.Idle>
            <IconFileText size={48} stroke={1.5} />
          </Dropzone.Idle>
          <div>
            <Text size="lg">Drag the case file here, or click to choose it</Text>
            <Text size="sm" c="dimmed">
              PDF, Word (.docx) or plain text, up to {MAX_MB} MB. A 20-page PDF takes about 10–20 seconds.
            </Text>
          </div>
        </Group>
      </Dropzone>
      {rejected && <ErrorAlert error={new Error(rejected)} />}
      {upload.error && <ErrorAlert error={upload.error} />}
      <List size="sm" c="dimmed" spacing={4}>
        <List.Item>The file is private to you, and is not added to the historical cases.</List.Item>
        <List.Item>Delete it from its results page when you have finished.</List.Item>
        <List.Item>
          Scanned documents without a text layer can't be read yet (OCR is not supported).
        </List.Item>
        <List.Item>
          For a test, use the fictional sample <code>samples/CASE-1042-fictional.txt</code> in the project folder.
        </List.Item>
      </List>
    </Stack>
  )
}
