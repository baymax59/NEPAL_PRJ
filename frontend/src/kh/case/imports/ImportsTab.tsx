// Imported findings: what outside systems (Log Analyzer, CDR/IPDR analysis, OSINT, alerts) added to the
// case, each kept exactly as received with where it came from, and the identifiers they share with other cases.

import { Badge, Button, Chip, Group, Paper, Stack, Tabs, Text } from '@mantine/core'
import { IconFingerprint, IconListDetails, IconPlugConnected } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useSearchParams } from 'react-router'
import { kh } from '../../api'
import type { ImportItem, ImportsView } from '../../types'
import { EmptyState, Loaded, PersonName, When } from '../../ui'
import { useCase } from '../context'
import { AddFromSourceDialog } from './AddFromSourceDialog'
import { periodText, itemColor } from './format'
import { ImportDrawer } from './ImportDrawer'
import { IndicatorsView } from './IndicatorsView'

const VIEWS = [
  { value: 'findings', label: 'Findings', icon: <IconListDetails size={15} /> },
  { value: 'indicators', label: 'Indicators', icon: <IconFingerprint size={15} /> },
]

export function ImportsTab() {
  const detail = useCase()
  const [params, setParams] = useSearchParams()
  const view = VIEWS.some((v) => v.value === params.get('view')) ? params.get('view')! : 'findings'
  const opened = params.get('finding')
  const [adding, setAdding] = useState(false)
  const canWrite = detail.can.add_files
  const set = (key: string, value: string | null) =>
    setParams(
      (current) => {
        const updated = new URLSearchParams(current)
        if (value) updated.set(key, value)
        else updated.delete(key)
        return updated
      },
      { replace: true },
    )
  return (
    <Stack gap="sm">
      <Group justify="space-between" wrap="wrap" gap="xs">
        <span />
        <Group gap="xs">
          <Tabs value={view} onChange={(v) => v && set('view', v)} variant="pills" radius="sm">
            <Tabs.List>
              {VIEWS.map((v) => (
                <Tabs.Tab key={v.value} value={v.value} leftSection={v.icon}>
                  {v.label}
                </Tabs.Tab>
              ))}
            </Tabs.List>
          </Tabs>
          {canWrite && (
            <Button size="xs" leftSection={<IconPlugConnected size={15} />} onClick={() => setAdding(true)}>
              Add from a source
            </Button>
          )}
        </Group>
      </Group>
      <Text size="xs" c="dimmed">
        Findings added by outside systems through the "Add to case" connection. Each is kept exactly as received, with its source, its record ID
        and the legal authority it was obtained under. Raw data (logs, call or IP records) stays in its source system.
      </Text>
      {view === 'findings' && <FindingsView caseId={detail.id} onOpen={(id) => set('finding', id)} />}
      {view === 'indicators' && <IndicatorsView detail={detail} onOpen={(id) => set('finding', id)} />}
      {opened && <ImportDrawer detail={detail} artifactId={opened} onClose={() => set('finding', null)} />}
      {adding && <AddFromSourceDialog detail={detail} onClose={() => setAdding(false)} />}
    </Stack>
  )
}

function FindingsView({ caseId, onOpen }: { caseId: string; onOpen: (artifactId: string) => void }) {
  const query = useQuery({ queryKey: ['kh', 'case', caseId, 'imports'], queryFn: () => kh.imports(caseId) })
  const [types, setTypes] = useState<string[]>([])
  return (
    <Loaded query={query}>
      {(data: ImportsView) => {
        const shown = types.length ? data.imports.filter((i) => types.includes(i.item_type ?? '')) : data.imports
        const present = data.item_types.filter((t) => data.imports.some((i) => i.item_type === t.code))
        if (!data.imports.length) {
          return (
            <EmptyState title="No imported findings yet" icon={<IconPlugConnected size={22} />}>
              Log events, alerts, CDR and IPDR results, open-source information, indicators and external reports appear here once a connected
              system adds them to this case.
            </EmptyState>
          )
        }
        return (
          <Stack gap="sm">
            {present.length > 1 && (
              <Chip.Group multiple value={types} onChange={setTypes}>
                <Group gap={6}>
                  {present.map((t) => (
                    <Chip key={t.code} value={t.code} size="xs" color={itemColor(t.code)} variant="light">
                      {t.label} ({data.imports.filter((i) => i.item_type === t.code).length})
                    </Chip>
                  ))}
                </Group>
              </Chip.Group>
            )}
            {shown.map((item) => (
              <FindingCard key={item.artifact_id} item={item} onOpen={() => onOpen(item.artifact_id)} />
            ))}
          </Stack>
        )
      }}
    </Loaded>
  )
}

function FindingCard({ item, onOpen }: { item: ImportItem; onOpen: () => void }) {
  const withdrawn = item.status !== 'active'
  return (
    <Paper
      withBorder
      p="sm"
      radius="md"
      onClick={onOpen}
      style={{ cursor: 'pointer', opacity: withdrawn ? 0.65 : 1 }}
      role="button"
      tabIndex={0}
      onKeyDown={(event) => event.key === 'Enter' && onOpen()}
      aria-label={`Open ${item.display_id}: ${item.title}`}
    >
      <Stack gap={6}>
        <Group gap={6} wrap="wrap">
          <Badge color={itemColor(item.item_type)} variant="light" size="sm">
            {item.item_type_label}
          </Badge>
          <Text size="sm" ff="monospace" c="dimmed">
            {item.display_id}
          </Text>
          <Text size="sm" fw={600} style={{ flex: 1, minWidth: 200 }}>
            {item.title}
          </Text>
          {item.versions > 1 && (
            <Badge variant="outline" color="gray" size="sm">
              version {item.version_number} of {item.versions}
            </Badge>
          )}
          {withdrawn && (
            <Badge color="gray" size="sm">
              withdrawn
            </Badge>
          )}
          {item.fictional && (
            <Badge color="yellow" variant="light" size="sm">
              fictional
            </Badge>
          )}
        </Group>
        <Text size="sm" lineClamp={3}>
          {item.summary}
        </Text>
        <Group gap="md" wrap="wrap">
          <Text size="xs" c="dimmed">
            From <b>{item.source.name}</b> · record <code>{item.source_record_id}</code>
          </Text>
          {item.observed_at && (
            <Text size="xs" c="dimmed">
              Happened {periodText(item.observed_at, item.observed_until)}
            </Text>
          )}
        </Group>
        {item.identifiers.length > 0 && (
          <Group gap={4} wrap="wrap">
            {item.identifiers.slice(0, 8).map((i) => (
              <Badge key={`${i.type}:${i.value}`} variant="default" size="sm" radius="sm" tt="none" fw={500}>
                {i.label}: {i.value}
              </Badge>
            ))}
            {item.identifiers.length > 8 && (
              <Text size="xs" c="dimmed">
                +{item.identifiers.length - 8} more
              </Text>
            )}
          </Group>
        )}
        <Group gap="sm" wrap="wrap" onClick={(event) => event.stopPropagation()}>
          <PersonName person={item.imported_by} size="xs" />
          <When at={item.imported_at} size="xs" />
        </Group>
      </Stack>
    </Paper>
  )
}
