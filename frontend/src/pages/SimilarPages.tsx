// Similar historical cases for an existing case (compare view) or for an uploaded new case.

import { Alert, Badge, Button, Center, Group, Loader, NumberInput, Paper, Stack, Text, Title } from '@mantine/core'
import { notifications } from '@mantine/notifications'
import { IconArrowLeft, IconInfoCircle, IconTrash } from '@tabler/icons-react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { deleteUpload, getCase, getUpload, similarToCase, similarToUpload } from '../api/endpoints'
import type { CaseFilters, SimilarCasesResponse } from '../api/types'
import { SimilarCaseCard, SimilarResultsHeader } from '../components/CaseCards'
import { ErrorAlert, Notices, RelevanceNote } from '../components/common'
import { formatBytes } from '../lib/format'

function YearFilter({ filters, onChange }: { filters: CaseFilters; onChange: (filters: CaseFilters) => void }) {
  return (
    <Group align="flex-end">
      <NumberInput
        label="Decided from"
        size="xs"
        w={120}
        min={1900}
        max={2100}
        value={filters.year_from ?? ''}
        onChange={(v) => onChange({ ...filters, year_from: typeof v === 'number' ? v : null })}
      />
      <NumberInput
        label="to"
        size="xs"
        w={120}
        min={1900}
        max={2100}
        value={filters.year_to ?? ''}
        onChange={(v) => onChange({ ...filters, year_to: typeof v === 'number' ? v : null })}
      />
    </Group>
  )
}

function Results({ data, newCaseLabel }: { data: SimilarCasesResponse; newCaseLabel: string }) {
  return (
    <Stack gap="md">
      <SimilarResultsHeader title="Similar historical cases" total={data.total_cases} />
      <Notices notices={data.notices} />
      {data.results.length > 0 ? (
        <RelevanceNote note={data.relevance_note} />
      ) : (
        <Alert color="gray" icon={<IconInfoCircle size={18} />}>
          No sufficiently similar cases were found among the cases you can see.
        </Alert>
      )}
      {data.results.map((item) => (
        <SimilarCaseCard key={item.case.display_id} item={item} note={data.relevance_note} newCaseLabel={newCaseLabel} />
      ))}
    </Stack>
  )
}

export function SimilarToCasePage() {
  const { displayId = '' } = useParams()
  const [filters, setFilters] = useState<CaseFilters>({})
  const selected = useQuery({ queryKey: ['case', displayId], queryFn: () => getCase(displayId) })
  const similar = useQuery({
    queryKey: ['similar-case', displayId, filters],
    queryFn: () => similarToCase(displayId, filters),
  })

  return (
    <Stack gap="md">
      <Group>
        <Button
          component={Link}
          to={`/cases/${displayId}`}
          variant="subtle"
          size="xs"
          leftSection={<IconArrowLeft size={14} />}
        >
          Back to case details
        </Button>
      </Group>
      <div>
        <Text size="sm" c="dimmed">
          Compare: cases similar to the selected case
        </Text>
        <Title order={1} size="h3">
          {selected.data?.title ?? displayId}
        </Title>
      </div>
      <YearFilter filters={filters} onChange={setFilters} />
      {similar.isFetching && <Loader size="sm" />}
      {similar.error && <ErrorAlert error={similar.error} />}
      {similar.data && <Results data={similar.data} newCaseLabel="Selected case" />}
    </Stack>
  )
}

export function UploadResultsPage() {
  const { uploadId = '' } = useParams()
  const navigate = useNavigate()
  const [filters, setFilters] = useState<CaseFilters>({})
  const upload = useQuery({ queryKey: ['upload', uploadId], queryFn: () => getUpload(uploadId) })
  const similar = useQuery({
    queryKey: ['similar-upload', uploadId, filters],
    queryFn: () => similarToUpload(uploadId, filters),
    enabled: upload.isSuccess,
  })
  const remove = useMutation({
    mutationFn: () => deleteUpload(uploadId),
    onSuccess: () => {
      notifications.show({ message: 'The uploaded file and everything derived from it were deleted.' })
      navigate('/new')
    },
  })

  if (upload.isPending) {
    return (
      <Center py="xl">
        <Loader />
      </Center>
    )
  }
  if (upload.error) return <ErrorAlert error={upload.error} />
  const info = upload.data

  return (
    <Stack gap="md">
      <Paper withBorder p="lg" radius="md">
        <Group justify="space-between" align="flex-start">
          <div>
            <Text size="sm" c="dimmed">
              New case
            </Text>
            <Title order={1} size="h3">
              {info.filename}
            </Title>
            <Text size="sm" c="dimmed">
              {formatBytes(info.size_bytes)} · {info.page_count ? `${info.page_count} pages` : 'no page numbers'} ·{' '}
              {info.passages} passages
            </Text>
          </div>
          <Button
            color="red"
            variant="light"
            leftSection={<IconTrash size={16} />}
            loading={remove.isPending}
            onClick={() => {
              if (window.confirm('Delete this uploaded file and everything derived from it?')) remove.mutate()
            }}
          >
            Delete upload
          </Button>
        </Group>
        <Group gap="xs" mt="sm">
          <Text size="sm" fw={500}>
            Provisions detected:
          </Text>
          {info.provisions.length === 0 ? (
            <Text size="sm" c="dimmed">
              none
            </Text>
          ) : (
            info.provisions.map((p) => (
              <Badge key={p.key} variant="light" color="gray" tt="none">
                {p.label}
              </Badge>
            ))
          )}
        </Group>
        {info.warnings.map((w) => (
          <Text key={w} size="sm" c="orange" mt="xs">
            {w}
          </Text>
        ))}
        {remove.error && <ErrorAlert error={remove.error} />}
      </Paper>
      <YearFilter filters={filters} onChange={setFilters} />
      {similar.isFetching && (
        <Group>
          <Loader size="sm" />
          <Text size="sm" c="dimmed">
            Comparing with the historical cases…
          </Text>
        </Group>
      )}
      {similar.error && <ErrorAlert error={similar.error} />}
      {similar.data && <Results data={similar.data} newCaseLabel="New case" />}
    </Stack>
  )
}
