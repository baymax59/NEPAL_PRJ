// Choosing a colleague.

import { Badge, Group, Select, Text } from '@mantine/core'
import { useDebouncedValue } from '@mantine/hooks'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { kh } from './api'
import { roleLabel } from './labels'
import type { Colleague } from './types'

/** A searchable list of colleagues the user could choose (the backend lists only suitable people). */
export function ColleagueSelect({
  purpose,
  classification,
  caseId,
  stationId,
  value,
  onChange,
  label,
  description,
  placeholder = 'Type a name…',
  required,
  clearable = true,
}: {
  purpose: 'lead' | 'supervisor' | 'team'
  classification?: string
  caseId?: string // to add someone to a team: the case
  stationId?: string // for a new case: only people who work at this station are offered
  value: Colleague | null
  onChange: (person: Colleague | null) => void
  label: string
  description?: string
  placeholder?: string
  required?: boolean
  clearable?: boolean
}) {
  const [search, setSearch] = useState('')
  const [debounced] = useDebouncedValue(search, 250)
  const query = useQuery({
    queryKey: ['kh', 'colleagues', purpose, classification, caseId, stationId, debounced],
    queryFn: () => kh.colleagues({ purpose, classification, case_id: caseId, q: debounced || undefined, station_id: stationId }),
    enabled: purpose === 'team' ? Boolean(caseId) : Boolean(classification),
    staleTime: 30_000,
  })
  const people = query.data ?? []
  const options = [...(value && !people.some((p) => p.id === value.id) ? [value] : []), ...people]
  return (
    <Select
      label={label}
      description={description}
      placeholder={placeholder}
      required={required}
      searchable
      clearable={clearable}
      searchValue={search}
      onSearchChange={setSearch}
      filter={({ options: all }) => all}
      nothingFoundMessage={query.isFetching ? 'Searching…' : 'Nobody suitable found'}
      data={options.map((p) => ({ value: p.id, label: `${p.display_name} (@${p.username})` }))}
      value={value?.id ?? null}
      onChange={(id) => onChange(options.find((p) => p.id === id) ?? null)}
      renderOption={({ option }) => {
        const person = options.find((p) => p.id === option.value)
        return (
          <Group gap="xs" justify="space-between" w="100%" wrap="nowrap">
            <Text size="sm">{option.label}</Text>
            <Badge size="xs" color="gray">
              {roleLabel(person?.org_role)}
            </Badge>
          </Group>
        )
      }}
    />
  )
}
