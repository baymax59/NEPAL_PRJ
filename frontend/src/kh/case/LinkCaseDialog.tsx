// Link this case to another investigation or to a past case of the knowledge base, with a reason.
// Used by Similar cases (CM-5) and by shared identifiers of imported findings (CM-6).

import { Button, Group, Modal, Select, Stack, Text, Textarea } from '@mantine/core'
import { IconLink } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { kh } from '../api'
import { toastDone, toastError, useOnceKey } from '../feedback'
import type { CaseDetail } from '../types'
import { useRefreshCase } from './helpers'

export type LinkTarget = { kind: 'case'; id: string; label: string } | { kind: 'knowledge'; id: string; label: string }

export function LinkCaseDialog({
  detail,
  target,
  onClose,
  initialType,
  initialReason = '',
  hint = 'Similar text does not make two cases the same: say what actually connects them.',
}: {
  detail: CaseDetail
  target: LinkTarget
  onClose: () => void
  initialType?: string
  initialReason?: string
  hint?: string
}) {
  const client = useQueryClient()
  const refresh = useRefreshCase(detail.id)
  const [key, renew] = useOnceKey()
  const links = useQuery({ queryKey: ['kh', 'case', detail.id, 'links'], queryFn: () => kh.links(detail.id) })
  const types = links.data?.link_types ?? []
  const [type, setType] = useState<string | null>(initialType ?? null)
  const [reason, setReason] = useState(initialReason)
  const chosenType = type ?? (target.kind === 'knowledge' ? 'same_method' : 'related')
  const mutation = useMutation({
    mutationFn: () => {
      const body = {
        link_type: chosenType as 'related',
        reason: reason.trim(),
        ...(target.kind === 'case' ? { target_case_id: target.id } : { knowledge_case: target.id }),
      }
      return kh.addLink(detail.id, body, key)
    },
    onSuccess: () => {
      renew()
      refresh()
      client.invalidateQueries({ queryKey: ['kh', 'case', detail.id] })
      toastDone('Case linked')
      onClose()
    },
    onError: (error) => toastError(error, 'Not linked'),
  })
  return (
    <Modal opened onClose={onClose} size="lg" title={<Text fw={600}>Link {target.label} to {detail.display_id}</Text>}>
      <Stack gap="sm">
        <Select
          label="How are they related?"
          data={types.map((t) => ({ value: t.code, label: t.label }))}
          value={chosenType}
          onChange={setType}
          allowDeselect={false}
          disabled={!types.length}
        />
        <Textarea
          label="Reason"
          description="In your own words, after checking the facts: at least 10 characters. It stays with the link."
          value={reason}
          onChange={(e) => setReason(e.currentTarget.value)}
          autosize
          minRows={3}
          maxLength={1000}
          required
        />
        <Text size="xs" c="dimmed">
          The link is added to the case at once, and stays in the history even if it is withdrawn later. {hint}
        </Text>
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={reason.trim().length < 10} loading={mutation.isPending} onClick={() => mutation.mutate()} leftSection={<IconLink size={16} />}>
            Link
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}
