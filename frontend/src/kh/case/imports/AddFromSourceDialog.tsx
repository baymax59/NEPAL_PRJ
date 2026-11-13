// "Add to case" from a connected system. Until the real Log Analyzer, CDR/IPDR, OSINT and alert systems exist, the
// fictional test source stands in for them: it offers invented findings and adds them through the same rules.

import { Alert, Badge, Button, Group, Modal, Paper, ScrollArea, Stack, Text } from '@mantine/core'
import { IconCheck, IconFlask, IconPlus } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { ApiError } from '../../../api/client'
import { kh } from '../../api'
import { toastDone, toastError, useOnceKey } from '../../feedback'
import type { CaseDetail, TestFinding } from '../../types'
import { Loaded } from '../../ui'
import { useRefreshCase } from '../helpers'
import { itemColor, periodText } from './format'

export function AddFromSourceDialog({ detail, onClose }: { detail: CaseDetail; onClose: () => void }) {
  const client = useQueryClient()
  const refresh = useRefreshCase(detail.id)
  const [key, renew] = useOnceKey()
  const source = useQuery({ queryKey: ['kh', 'test-source'], queryFn: () => kh.testSource(), retry: false })
  const [sent, setSent] = useState<Record<string, string>>({})
  const send = useMutation({
    mutationFn: (finding: TestFinding) => kh.sendTestFinding({ finding_id: finding.id, case_id: detail.id }, key),
    onSuccess: (added, finding) => {
      renew()
      refresh()
      client.invalidateQueries({ queryKey: ['kh', 'case', detail.id] })
      setSent((current) => ({ ...current, [finding.id]: added.finding.display_id }))
      toastDone(
        `${added.finding.display_id}${added.updated ? ` version ${added.finding.version_number}` : ''} added to the case`,
      )
    },
    onError: (error) => toastError(error, 'Not added'),
  })
  const turnedOff = source.error instanceof ApiError && source.error.status === 404
  return (
    <Modal opened onClose={onClose} size="xl" title={<Text fw={600}>Add to {detail.display_id} from a connected system</Text>}>
      {turnedOff ? (
        <Alert color="gray">No connected system is available here. The fictional test source is turned off on this server.</Alert>
      ) : (
        <Loaded query={source}>
          {(data) => (
            <Stack gap="sm">
              <Alert color="yellow" variant="light" icon={<IconFlask size={18} />} title="Fictional test source">
                {data.note} In the real platform, the "Add to case" button is in those systems: they use the same connection, and the same rules
                apply (your rights in the case, the source's policy, an entry in the history and an audit record).
              </Alert>
              {!data.registered ? (
                <Alert color="gray">A platform administrator first registers the fictional test source, under Administration, Integration sources.</Alert>
              ) : (
                <>
                  <ScrollArea.Autosize mah={480} offsetScrollbars>
                    <Stack gap="xs">
                      {data.findings.map((f) => (
                        <Paper key={f.id} withBorder p="sm" radius="md">
                          <Group justify="space-between" align="flex-start" wrap="nowrap" gap="sm">
                            <Stack gap={4} style={{ minWidth: 0 }}>
                              <Group gap={6}>
                                <Badge color={itemColor(f.item_type)} variant="light" size="sm">
                                  {f.item_type_label}
                                </Badge>
                                <Text size="xs" c="dimmed">
                                  {f.system} · {f.source_record_id}
                                </Text>
                              </Group>
                              <Text size="sm" fw={600}>
                                {f.title}
                              </Text>
                              <Text size="xs" c="dimmed" lineClamp={2}>
                                {f.summary}
                              </Text>
                              {f.updates && (
                                <Text size="xs" c="orange">
                                  A later version of the same record: the source changed it. Adding it keeps the first version.
                                </Text>
                              )}
                              {f.observed_at && (
                                <Text size="xs" c="dimmed">
                                  Happened {periodText(f.observed_at, f.observed_until)}
                                  {f.authority_ref ? ` · ${f.authority_ref}` : ''}
                                </Text>
                              )}
                            </Stack>
                            {sent[f.id] ? (
                              <Group gap={4} wrap="nowrap" c="teal" style={{ flexShrink: 0 }}>
                                <IconCheck size={14} />
                                <Text size="sm" fw={600} c="teal" style={{ whiteSpace: 'nowrap' }}>
                                  added as {sent[f.id]}
                                </Text>
                              </Group>
                            ) : (
                              <Button
                                size="xs"
                                variant="light"
                                style={{ flexShrink: 0 }}
                                leftSection={<IconPlus size={14} />}
                                loading={send.isPending && send.variables?.id === f.id}
                                onClick={() => send.mutate(f)}
                                aria-label={`Add ${f.source_record_id} to the case`}
                              >
                                Add to case
                              </Button>
                            )}
                          </Group>
                        </Paper>
                      ))}
                    </Stack>
                  </ScrollArea.Autosize>
                </>
              )}
            </Stack>
          )}
        </Loaded>
      )}
    </Modal>
  )
}
