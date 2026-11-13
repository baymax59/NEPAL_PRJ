// Evidence detail and integrity verification (spec §9, §20, §21 screen 8).

import { Alert, Anchor, Badge, Button, Grid, Group, Modal, Paper, ScrollArea, SegmentedControl, Stack, Text, TextInput, Textarea, Timeline, Title } from '@mantine/core'
import { IconDownload, IconEye, IconFingerprint, IconLock, IconLockOpen, IconShieldCheck, IconShieldX, IconTransfer } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useParams } from 'react-router'
import { formatBytes } from '../../lib/format'
import { kh } from '../api'
import { Comments } from '../Comments'
import { custodyLabel, humanize } from '../labels'
import { ColleagueSelect } from '../pickers'
import { withOffset } from '../case/helpers'
import type { Colleague, EvidenceDetail, VerificationOut } from '../types'
import { ClassificationBadge, ConfirmModal, Facts, IntegrityBadge, Loaded, Panel, PersonName, When } from '../ui'
import { toastDone, toastError } from '../feedback'
import { formatWhen } from '../time'

export function EvidencePage() {
  const { evidenceId = '' } = useParams()
  const query = useQuery({ queryKey: ['kh', 'evidence', evidenceId], queryFn: () => kh.evidence(evidenceId) })
  return <Loaded query={query}>{(item) => <EvidenceView item={item} />}</Loaded>
}

function EvidenceView({ item }: { item: EvidenceDetail }) {
  const queryClient = useQueryClient()
  const [result, setResult] = useState<VerificationOut | null>(null)
  const [dialog, setDialog] = useState<null | 'transfer' | 'decline' | 'seal' | 'unseal'>(null)
  const [showPreview, setShowPreview] = useState(false)
  const versions = useQuery({ queryKey: ['kh', 'evidence', item.id, 'versions'], queryFn: () => kh.evidenceVersions(item.id) })
  const custody = useQuery({ queryKey: ['kh', 'evidence', item.id, 'custody'], queryFn: () => kh.custody(item.id) })
  const preview = useQuery({ queryKey: ['kh', 'evidence', item.id, 'preview'], queryFn: () => kh.preview(item.id), enabled: showPreview })
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['kh', 'evidence', item.id] })

  const verify = useMutation({
    mutationFn: () => kh.verify(item.id),
    onSuccess: (checked) => {
      setResult(checked)
      refresh()
    },
    onError: (error) => toastError(error, 'Not verified'),
  })
  const download = useMutation({
    mutationFn: () => kh.downloadLink(item.id),
    onSuccess: (link) => {
      window.location.assign(link.url) // a one-time link, valid for a few minutes; integrity is checked again before sending
    },
    onError: (error) => toastError(error, 'No download link'),
  })
  const acknowledge = useMutation({
    mutationFn: () => kh.custodyAction(item.id, { action: 'acknowledge', transfer_event_id: item.pending_transfer?.id ?? null }),
    onSuccess: () => {
      toastDone('Receipt acknowledged: the exhibit was checked and is now in your custody')
      refresh()
    },
    onError: (error) => toastError(error),
  })
  const decline = useMutation({
    mutationFn: (reason: string) => kh.custodyAction(item.id, { action: 'decline', transfer_event_id: item.pending_transfer?.id ?? null, reason }),
    onSuccess: () => {
      toastDone('Handover declined')
      setDialog(null)
      refresh()
    },
    onError: (error) => toastError(error),
  })
  const seal = useMutation({
    mutationFn: ({ sealIt, reason }: { sealIt: boolean; reason: string }) => (sealIt ? kh.sealEvidence(item.id, reason) : kh.unsealEvidence(item.id, reason)),
    onSuccess: () => {
      toastDone('Done')
      setDialog(null)
      refresh()
    },
    onError: (error) => toastError(error),
  })

  return (
    <Stack gap="md">
      <Group gap="xs">
        <Anchor component={Link} to={`/kh/case/${item.case.id}/files`} size="sm">
          ← Case files
        </Anchor>
        <Text size="sm" c="dimmed">
          {item.case.display_id} · {item.case.title}
        </Text>
      </Group>
      <Paper withBorder p="md" radius="sm">
        <Group justify="space-between" align="flex-start">
          <Stack gap={6}>
            <Group gap="xs">
              <IconFingerprint size={22} color="var(--mantine-color-teal-5)" />
              <Text ff="monospace" fw={700} fz={18}>
                {item.display_id}
              </Text>
              <Badge color="teal">{humanize(item.evidence_type)}</Badge>
              {item.category !== item.evidence_type && <Badge color="gray">{humanize(item.category)}</Badge>}
              <ClassificationBadge value={item.classification} />
              {item.sealed && (
                <Badge color="orange" leftSection={<IconLock size={11} />}>
                  Sealed
                </Badge>
              )}
            </Group>
            <Title order={2} size="h3">
              {item.title}
            </Title>
            {item.description && (
              <Text size="sm" c="dimmed">
                {item.description}
              </Text>
            )}
          </Stack>
          <Group gap="xs">
            {item.can.preview && (
              <Button size="xs" variant="default" leftSection={<IconEye size={14} />} onClick={() => setShowPreview(true)}>
                Preview text
              </Button>
            )}
            {item.can.download && (
              <Button size="xs" variant="default" leftSection={<IconDownload size={14} />} loading={download.isPending} onClick={() => download.mutate()}>
                Download
              </Button>
            )}
            {item.can.seal && (
              <Button size="xs" variant="default" leftSection={<IconLock size={14} />} onClick={() => setDialog('seal')}>
                Seal
              </Button>
            )}
            {item.can.unseal && (
              <Button size="xs" variant="default" leftSection={<IconLockOpen size={14} />} onClick={() => setDialog('unseal')}>
                Unseal
              </Button>
            )}
          </Group>
        </Group>
        {item.active_content && (
          <Alert color="orange" mt="sm" p="xs">
            Active content (a program, script or web page): kept as evidence, never opened or previewed here.
          </Alert>
        )}
        {item.sealed && (
          <Alert color="orange" mt="sm" p="xs" icon={<IconLock size={16} />}>
            Sealed {item.sealed_at ? formatWhen(item.sealed_at) : ''} by {item.sealed_by?.display_name ?? '—'}: {item.sealed_reason}. Only the supervisor and administrators see it.
          </Alert>
        )}
      </Paper>

      <Grid gap="md">
        <Grid.Col span={{ base: 12, md: 7 }}>
          <Stack gap="md">
            <Panel
              title="Integrity"
              actions={
                item.can.verify && (
                  <Button size="xs" leftSection={<IconShieldCheck size={14} />} loading={verify.isPending} onClick={() => verify.mutate()}>
                    Verify integrity now
                  </Button>
                )
              }
            >
              <Stack gap="sm">
                {result && (
                  <Alert
                    color={result.result === 'match' ? 'green' : 'red'}
                    icon={result.result === 'match' ? <IconShieldCheck size={18} /> : <IconShieldX size={18} />}
                    title={result.result === 'match' ? 'File is original' : 'The file was changed'}
                  >
                    {result.result === 'match'
                      ? `The stored file was read again just now and is exactly the file that arrived.`
                      : result.result === 'missing'
                        ? 'The stored file is missing. This has been recorded; tell your administrator.'
                        : 'The stored file is no longer the file that arrived. This has been recorded; tell your administrator.'}
                  </Alert>
                )}
                <Facts
                  items={[
                    ['Latest check', item.last_check ? <Group key="c" gap={6}><IntegrityBadge result={item.last_check.result} /><When at={item.last_check.checked_at} size="xs" /></Group> : <IntegrityBadge key="n" result={null} />],
                    ['File', `${item.original_filename} · ${item.mime_type}`],
                    ['Size', formatBytes(item.size_bytes)],
                    ['Checked by', item.last_check ? `${item.last_check.checked_by?.display_name ?? 'scheduled check'} (${humanize(item.last_check.trigger)})` : null],
                    ['Stored', 'once, read-only; never overwritten'],
                  ]}
                />
              </Stack>
            </Panel>

            <Panel title="Provenance">
              <Facts
                items={[
                  ['Collected at', item.collected_at ? `${formatWhen(item.collected_at)}${item.collected_tz ? ` (${item.collected_tz})` : ''}` : null],
                  ['Collected by', item.collected_by],
                  ['Collection authority', item.collection_authority],
                  ['Source', item.source],
                  ['Uploaded', `${formatWhen(item.uploaded_at)} by ${item.uploaded_by?.display_name ?? '—'}`],
                  ['Folder', item.folder],
                ]}
              />
              {item.sources.length > 0 && (
                <Stack gap={4} mt="sm">
                  <Text size="xs" fw={600}>
                    Source system references
                  </Text>
                  {item.sources.map((s, i) => (
                    <Text key={i} size="xs" c="dimmed">
                      {s.source_system} {s.source_record_id ? `· ${s.source_record_id}` : ''} · imported {formatWhen(s.imported_at)}
                    </Text>
                  ))}
                </Stack>
              )}
            </Panel>

            <Panel title="Versions and derived work">
              <Loaded query={versions}>
                {(v) => (
                  <Stack gap="xs">
                    <Text size="sm">
                      <b>Original</b> ({v.original.original_filename}, {formatBytes(v.original.size_bytes)}), added to {item.case.display_id}. Original evidence never changes; work based on it is added as notes and analyses.
                    </Text>
                    {v.derived.length === 0 ? (
                      <Text size="xs" c="dimmed">
                        No analyses refer to it yet.
                      </Text>
                    ) : (
                      v.derived.map((d) => (
                        <Group key={d.version_id} gap="xs">
                          <Text size="sm" ff="monospace">
                            {d.display_id}
                          </Text>
                          <Text size="sm">{d.title}</Text>
                          <Badge size="xs" color="gray">
                            {humanize(d.artifact_type)} v{d.version_number}
                          </Badge>
                          <PersonName person={d.author} size="xs" />
                        </Group>
                      ))
                    )}
                  </Stack>
                )}
              </Loaded>
            </Panel>

            <Panel title="Comments">
              <Comments caseId={item.case.id} targetType="evidence" targetId={item.id} canWrite={item.can.add_derived} />
            </Panel>
          </Stack>
        </Grid.Col>

        <Grid.Col span={{ base: 12, md: 5 }}>
          <Panel
            title="Chain of custody"
            actions={
              item.can.transfer && (
                <Button size="xs" variant="light" leftSection={<IconTransfer size={14} />} onClick={() => setDialog('transfer')}>
                  Hand over
                </Button>
              )
            }
          >
            <Stack gap="sm">
              <Text size="sm">
                Current custodian: <b>{item.custodian ? (item.custodian.user?.display_name ?? item.custodian.name) : '—'}</b>
              </Text>
              {item.pending_transfer && (
                <Alert color="yellow" p="xs" icon={<IconTransfer size={16} />}>
                  <Stack gap={6}>
                    <Text size="sm">
                      Handover to {item.pending_transfer.to_custodian?.user?.display_name ?? item.pending_transfer.to_custodian?.name} is waiting for acknowledgement.
                    </Text>
                    {item.can.acknowledge && (
                      <Group gap="xs">
                        <Button size="xs" loading={acknowledge.isPending} onClick={() => acknowledge.mutate()}>
                          Acknowledge receipt
                        </Button>
                        <Button size="xs" variant="default" onClick={() => setDialog('decline')}>
                          Decline
                        </Button>
                      </Group>
                    )}
                  </Stack>
                </Alert>
              )}
              <Loaded query={custody}>
                {(c) => (
                  <Timeline bulletSize={14} lineWidth={2}>
                    {c.events.map((e) => (
                      <Timeline.Item key={e.id} color={e.event_type === 'declined' ? 'red' : e.event_type === 'transferred' ? 'yellow' : e.event_type === 'verified' ? 'green' : 'hawk'}>
                        <Text size="sm" fw={500}>
                          {custodyLabel(e.event_type)}
                        </Text>
                        <Text size="xs" c="dimmed">
                          {formatWhen(e.occurred_at)} · {e.actor?.display_name ?? '—'}
                        </Text>
                        {(e.from_custodian || e.to_custodian) && (
                          <Text size="xs">
                            {e.from_custodian ? (e.from_custodian.user?.display_name ?? e.from_custodian.name) : '—'} → {e.to_custodian ? (e.to_custodian.user?.display_name ?? e.to_custodian.name) : '—'}
                          </Text>
                        )}
                        {e.reason && (
                          <Text size="xs" c="dimmed">
                            “{e.reason}”
                          </Text>
                        )}
                        {e.method && (
                          <Text size="xs" c="dimmed">
                            Method: {e.method === 'sha256' ? 'automatic file check' : e.method}
                          </Text>
                        )}
                        {e.verification_sha256 && (
                          <Text size="xs" c={e.verification_sha256 === item.sha256 ? 'green' : 'red'}>
                            File check at that moment: {e.verification_sha256 === item.sha256 ? 'file was original' : 'file did NOT match'}
                          </Text>
                        )}
                      </Timeline.Item>
                    ))}
                  </Timeline>
                )}
              </Loaded>
            </Stack>
          </Panel>
        </Grid.Col>
      </Grid>

      <Modal opened={showPreview} onClose={() => setShowPreview(false)} size="xl" title={<Text fw={600}>Text of {item.display_id}</Text>}>
        <Loaded query={preview}>
          {(p) =>
            p.kind === 'none' ? (
              <Text size="sm" c="dimmed">
                {p.reason ?? 'No text preview for this kind of file.'}
              </Text>
            ) : (
              <ScrollArea.Autosize mah={560}>
                <Stack gap="sm">
                  {p.pages.map((page, i) => (
                    <Paper key={i} withBorder p="sm">
                      {page.number !== null && (
                        <Text size="xs" c="dimmed" mb={4}>
                          Page {page.number}
                        </Text>
                      )}
                      <Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>
                        {page.text}
                      </Text>
                    </Paper>
                  ))}
                  {p.truncated && (
                    <Text size="xs" c="dimmed">
                      The preview stops here; download the file for the rest.
                    </Text>
                  )}
                </Stack>
              </ScrollArea.Autosize>
            )
          }
        </Loaded>
      </Modal>
      {dialog === 'transfer' && <TransferDialog item={item} onClose={() => setDialog(null)} onDone={refresh} />}
      <ConfirmModal opened={dialog === 'decline'} onClose={() => setDialog(null)} title="Decline this handover?" confirmLabel="Decline" color="red" reason="required" loading={decline.isPending} onConfirm={(reason) => decline.mutate(reason)}>
        <Text size="sm">The exhibit stays with its current custodian. Your reason is kept in the chain of custody.</Text>
      </ConfirmModal>
      <ConfirmModal
        opened={dialog === 'seal' || dialog === 'unseal'}
        onClose={() => setDialog(null)}
        title={dialog === 'seal' ? `Seal ${item.display_id}?` : `Unseal ${item.display_id}?`}
        confirmLabel={dialog === 'seal' ? 'Seal' : 'Unseal'}
        reason="required"
        loading={seal.isPending}
        onConfirm={(reason) => seal.mutate({ sealIt: dialog === 'seal', reason })}
      >
        <Text size="sm">
          {dialog === 'seal'
            ? 'Only the supervisor and administrators will see the exhibit, in every report. It is recorded in the chain of custody.'
            : 'Everyone with access to the case will see the exhibit again. It is recorded in the chain of custody.'}
        </Text>
      </ConfirmModal>
    </Stack>
  )
}

function TransferDialog({ item, onClose, onDone }: { item: EvidenceDetail; onClose: () => void; onDone: () => void }) {
  const [to, setTo] = useState<'colleague' | 'external'>('colleague')
  const [person, setPerson] = useState<Colleague | null>(null)
  const [external, setExternal] = useState('')
  const [receipt, setReceipt] = useState('')
  const [reason, setReason] = useState('')
  const [method, setMethod] = useState('')
  const [authority, setAuthority] = useState('')
  const [when, setWhen] = useState('')
  const mutation = useMutation({
    mutationFn: () =>
      kh.custodyAction(item.id, {
        action: 'transfer',
        to_user_id: to === 'colleague' ? (person?.id ?? null) : null,
        to_external: to === 'external' ? external.trim() : null,
        receipt_reference: receipt.trim() || null,
        reason: reason.trim() || null,
        method: method.trim() || null,
        authorization_ref: authority.trim() || null,
        occurred_at: withOffset(when),
      }),
    onSuccess: () => {
      toastDone(to === 'colleague' ? 'Handover recorded: waiting for the receiver to acknowledge' : 'Handover recorded')
      onDone()
      onClose()
    },
    onError: (error) => toastError(error, 'Not handed over'),
  })
  const ready = to === 'colleague' ? Boolean(person) : external.trim().length > 2
  return (
    <Modal opened onClose={onClose} size="lg" title={<Text fw={600}>Hand over {item.display_id}</Text>}>
      <Stack gap="sm">
        <SegmentedControl value={to} onChange={(v) => setTo(v as 'colleague' | 'external')} data={[{ value: 'colleague', label: 'To a colleague' }, { value: 'external', label: 'To an outside body' }]} />
        {to === 'colleague' ? (
          <ColleagueSelect purpose="lead" classification={item.classification} label="Receiver" description="They must acknowledge receipt; until then you stay the custodian." value={person} onChange={setPerson} required />
        ) : (
          <>
            <TextInput label="Outside body" placeholder="e.g. Forensic laboratory, court property room" value={external} onChange={(e) => setExternal(e.currentTarget.value)} required />
            <TextInput label="Receipt reference" value={receipt} onChange={(e) => setReceipt(e.currentTarget.value)} />
          </>
        )}
        <Textarea label="Reason" value={reason} onChange={(e) => setReason(e.currentTarget.value)} autosize minRows={2} />
        <Group grow>
          <TextInput label="Method" placeholder="e.g. Hand delivery, sealed envelope" value={method} onChange={(e) => setMethod(e.currentTarget.value)} />
          <TextInput label="Authorisation" placeholder="e.g. Order or letter number" value={authority} onChange={(e) => setAuthority(e.currentTarget.value)} />
        </Group>
        <TextInput label="When (empty: now)" type="datetime-local" value={when} onChange={(e) => setWhen(e.currentTarget.value)} />
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={!ready} loading={mutation.isPending} onClick={() => mutation.mutate()} leftSection={<IconTransfer size={16} />}>
            Record handover
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}
