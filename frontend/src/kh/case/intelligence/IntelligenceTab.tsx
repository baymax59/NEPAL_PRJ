// Case Intelligence inside the case: similar cases, search, the assistant, the timeline and offence sections,
// all on the case as it stands now, and only on what you may see.

import { Group, Stack, Tabs } from '@mantine/core'
import { IconFileSearch, IconMessageChatbot, IconScale, IconTimelineEvent, IconTopologyStar3 } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router'
import { kh } from '../../api'
import { toastDone, toastError } from '../../feedback'
import { useCase } from '../context'
import { AssistantView } from './AssistantView'
import { CoverageBar } from './common'
import { OffencesView } from './OffencesView'
import { SearchView } from './SearchView'
import { SimilarView } from './SimilarView'
import { TimelineView } from './TimelineView'

const VIEWS = [
  { value: 'similar', label: 'Similar cases', icon: <IconTopologyStar3 size={15} /> },
  { value: 'search', label: 'Search', icon: <IconFileSearch size={15} /> },
  { value: 'assistant', label: 'Assistant', icon: <IconMessageChatbot size={15} /> },
  { value: 'timeline', label: 'Timeline', icon: <IconTimelineEvent size={15} /> },
  { value: 'offences', label: 'Offence sections', icon: <IconScale size={15} /> },
]

export function IntelligenceTab() {
  const detail = useCase()
  const client = useQueryClient()
  const [params, setParams] = useSearchParams()
  const view = VIEWS.some((v) => v.value === params.get('view')) ? params.get('view')! : 'similar'
  const status = useQuery({ queryKey: ['kh', 'case', detail.id, 'ci', 'status'], queryFn: () => kh.intelligence(detail.id) })
  const prepare = useMutation({
    mutationFn: () => kh.prepareIntelligence(detail.id),
    onSuccess: (result) => {
      client.invalidateQueries({ queryKey: ['kh', 'case', detail.id, 'ci'] })
      const left = result.coverage.pending.length
      toastDone(left ? `Read ${result.coverage.indexed} documents; ${left} still waiting (try again)` : 'Everything you may see here has been read')
    },
    onError: (error) => toastError(error, 'Not read'),
  })
  const show = (next: string | null) =>
    next &&
    setParams(
      (current) => {
        const updated = new URLSearchParams(current)
        updated.set('view', next)
        return updated
      },
      { replace: true },
    )
  return (
    <Stack gap="sm">
      <Group justify="space-between" wrap="wrap" gap="xs">
        <span />
        <Tabs value={view} onChange={show} variant="pills" radius="sm">
          <Tabs.List>
            {VIEWS.map((v) => (
              <Tabs.Tab key={v.value} value={v.value} leftSection={v.icon}>
                {v.label}
              </Tabs.Tab>
            ))}
          </Tabs.List>
        </Tabs>
      </Group>
      <CoverageBar coverage={status.data?.coverage} onPrepare={() => prepare.mutate()} preparing={prepare.isPending} />
      {view === 'similar' && <SimilarView detail={detail} />}
      {view === 'search' && <SearchView detail={detail} />}
      {view === 'assistant' && <AssistantView detail={detail} />}
      {view === 'timeline' && <TimelineView detail={detail} />}
      {view === 'offences' && <OffencesView detail={detail} />}
    </Stack>
  )
}
