// A case's legal holds and retention decisions (phase CM-7). Holds block archiving and disposal decisions; a retention
// decision is proposed by one person and decided by another; nothing in Knight Hawk is ever deleted.

import { Alert, Badge, Button, Group, Modal, Select, Stack, Text, Textarea, TextInput } from '@mantine/core'
import { IconGavel, IconLock } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { kh } from '../api'
import { toastDone, toastError } from '../feedback'
import type { CaseGovernance, RetentionDecisionOut } from '../types'
import { ConfirmModal, Loaded, Panel, PersonName } from '../ui'
import { formatDay, formatWhen } from '../time'

const STATUS_COLORS: Record<string, string> = { proposed: 'yellow', approved: 'teal', rejected: 'red', withdrawn: 'gray' }

export function CaseGovernancePanel({ caseId }: { caseId: string }) {
  const client = useQueryClient()
  const query = useQuery({ queryKey: ['kh', 'case', caseId, 'governance'], queryFn: () => kh.caseGovernance(caseId) })
  const [dialog, setDialog] = useState<'hold' | 'propose' | null>(null)
  const [releasing, setReleasing] = useState<string | null>(null)
  const refresh = () => {
    client.invalidateQueries({ queryKey: ['kh', 'case', caseId] })
  }
  const release = useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) => kh.releaseHold(id, reason),
    onSuccess: () => {
      setReleasing(null)
      refresh()
      toastDone('Legal hold released: it stays in the history')
    },
    onError: (error) => toastError(error, 'Not released'),
  })
  return (
    <Loaded query={query}>
      {(g: CaseGovernance) => (
        <Panel
          title="Legal holds and retention"
          actions={
            g.can_decide ? (
              <Group gap={4}>
                <Button size="compact-xs" variant="light" color="orange" leftSection={<IconLock size={12} />} onClick={() => setDialog('hold')}>
                  Place a hold
                </Button>
                <Button size="compact-xs" variant="default" leftSection={<IconGavel size={12} />} onClick={() => setDialog('propose')}>
                  Propose a decision
                </Button>
              </Group>
            ) : undefined
          }
        >
          <Stack gap="sm">
            {g.on_hold && (
              <Alert color="orange" variant="light" p="xs" icon={<IconLock size={16} />} title="Under a legal hold">
                <Text size="xs">The case can't be archived, and no decision to archive, transfer or dispose of it can be approved, until every hold is released.</Text>
              </Alert>
            )}
            {g.holds.length === 0 && g.decisions.length === 0 && (
              <Text size="sm" c="dimmed">
                No legal hold or retention decision. Nothing in Knight Hawk is ever deleted automatically.
              </Text>
            )}
            {g.holds.map((h) => (
              <Stack key={h.id} gap={2}>
                <Group gap={6}>
                  <Badge size="sm" color={h.active ? 'orange' : 'gray'} variant="light">
                    {h.active ? 'hold active' : 'hold released'}
                  </Badge>
                  {h.authority_ref && <Text size="xs">{h.authority_ref}</Text>}
                </Group>
                <Text size="xs">{h.reason}</Text>
                <Text size="xs" c="dimmed">
                  Placed {formatWhen(h.placed_at)} by {h.placed_by?.display_name ?? '—'}
                  {h.released_at ? ` · released ${formatWhen(h.released_at)} by ${h.released_by?.display_name ?? '—'}: “${h.release_reason}”` : ''}
                </Text>
                {h.active && g.can_decide && (
                  <Button size="compact-xs" variant="subtle" w="fit-content" onClick={() => setReleasing(h.id)}>
                    Release
                  </Button>
                )}
              </Stack>
            ))}
            {g.decisions.map((d) => (
              <DecisionRow key={d.id} decision={d} canDecide={g.can_decide} onChanged={refresh} />
            ))}
            {(g.policy || g.review_due_on) && (
              <Text size="xs" c="dimmed">
                {g.policy ? `Policy: ${g.policy.name}. ` : ''}
                {g.review_due_on ? `Retention review ${g.review_due ? 'due since' : 'due on'} ${formatDay(g.review_due_on)}.` : ''}
              </Text>
            )}
          </Stack>
          {dialog === 'hold' && <HoldDialog caseId={caseId} onClose={() => setDialog(null)} onDone={refresh} />}
          {dialog === 'propose' && <ProposeDialog caseId={caseId} governance={g} onClose={() => setDialog(null)} onDone={refresh} />}
          <ConfirmModal
            opened={releasing !== null}
            onClose={() => setReleasing(null)}
            title="Release the legal hold?"
            confirmLabel="Release"
            reason="required"
            minReason={10}
            loading={release.isPending}
            onConfirm={(reason) => releasing && release.mutate({ id: releasing, reason })}
          >
            <Text size="sm">The hold stays in the history, with your reason. The case can then be archived again.</Text>
          </ConfirmModal>
        </Panel>
      )}
    </Loaded>
  )
}

function DecisionRow({ decision: d, canDecide, onChanged }: { decision: RetentionDecisionOut; canDecide: boolean; onChanged: () => void }) {
  const [deciding, setDeciding] = useState<boolean | null>(null)
  const decide = useMutation({
    mutationFn: (note: string) => kh.decideRetention(d.id, deciding === true, note),
    onSuccess: (result) => {
      setDeciding(null)
      onChanged()
      toastDone(`Decision ${result.status}`)
    },
    onError: (error) => toastError(error, 'Not decided'),
  })
  return (
    <Stack gap={2}>
      <Group gap={6}>
        <Badge size="sm" color={STATUS_COLORS[d.status] ?? 'gray'} variant="light">
          {d.status}
        </Badge>
        <Text size="xs" fw={600}>
          {d.action_label}
        </Text>
      </Group>
      <Text size="xs">{d.reason}</Text>
      <Group gap={6}>
        <Text size="xs" c="dimmed">
          Proposed {formatWhen(d.proposed_at)} by
        </Text>
        <PersonName person={d.proposed_by} size="xs" />
        {d.decided_by && (
          <>
            <Text size="xs" c="dimmed">
              · decided by
            </Text>
            <PersonName person={d.decided_by} size="xs" />
          </>
        )}
      </Group>
      {d.review_on && <Text size="xs" c="dimmed">Next review: {formatDay(d.review_on)}</Text>}
      {d.transfer_to && <Text size="xs" c="dimmed">To: {d.transfer_to}</Text>}
      {d.decision_note && <Text size="xs" c="dimmed">“{d.decision_note}”</Text>}
      {d.outside_action && (
        <Alert color="gray" variant="light" p={6}>
          <Text size="xs">Approved for disposal. Knight Hawk keeps every record: carrying out a disposal is your organisation's own formal process.</Text>
        </Alert>
      )}
      {d.status === 'proposed' && canDecide && (
        <Group gap={4}>
          <Button size="compact-xs" variant="light" color="teal" onClick={() => setDeciding(true)}>
            Approve
          </Button>
          <Button size="compact-xs" variant="light" color="red" onClick={() => setDeciding(false)}>
            Reject
          </Button>
        </Group>
      )}
      <ConfirmModal
        opened={deciding !== null}
        onClose={() => setDeciding(null)}
        title={deciding ? 'Approve the retention decision?' : 'Reject the retention decision?'}
        confirmLabel={deciding ? 'Approve' : 'Reject'}
        color={deciding ? 'teal' : 'red'}
        reason="required"
        reasonLabel="Your note (kept with the decision)"
        loading={decide.isPending}
        onConfirm={(note) => decide.mutate(note)}
      >
        <Text size="sm">A second person decides: whoever proposed it can't. {d.action === 'archive' && deciding ? 'Approving archives the case and makes the case read-only; nothing is deleted.' : ''}</Text>
      </ConfirmModal>
    </Stack>
  )
}

function HoldDialog({ caseId, onClose, onDone }: { caseId: string; onClose: () => void; onDone: () => void }) {
  const [reason, setReason] = useState('')
  const [authority, setAuthority] = useState('')
  const place = useMutation({
    mutationFn: () => kh.placeHold(caseId, { reason: reason.trim(), authority_ref: authority.trim() || null }),
    onSuccess: () => {
      onDone()
      toastDone('Legal hold placed')
      onClose()
    },
    onError: (error) => toastError(error, 'No hold placed'),
  })
  return (
    <Modal opened onClose={onClose} title={<Text fw={600}>Place a legal hold</Text>}>
      <Stack gap="sm">
        <Textarea label="Reason" description="At least 10 characters; it stays with the hold." value={reason} onChange={(e) => setReason(e.currentTarget.value)} autosize minRows={2} required />
        <TextInput label="Order or instruction (optional)" value={authority} onChange={(e) => setAuthority(e.currentTarget.value)} maxLength={300} />
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button color="orange" disabled={reason.trim().length < 10} loading={place.isPending} onClick={() => place.mutate()}>
            Place the hold
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}

function ProposeDialog({ caseId, governance, onClose, onDone }: { caseId: string; governance: CaseGovernance; onClose: () => void; onDone: () => void }) {
  const [action, setAction] = useState<string | null>('retain')
  const [reason, setReason] = useState('')
  const [reviewOn, setReviewOn] = useState('')
  const [today] = useState(() => new Date().toISOString().slice(0, 10))
  const [transferTo, setTransferTo] = useState('')
  const propose = useMutation({
    mutationFn: () =>
      kh.proposeRetention(caseId, {
        action: (action ?? 'retain') as 'retain',
        reason: reason.trim(),
        review_on: action === 'retain' && reviewOn ? reviewOn : null,
        transfer_to: action === 'transfer' ? transferTo.trim() : null,
        policy_id: governance.policy?.id ?? null,
      }),
    onSuccess: () => {
      onDone()
      toastDone('Retention decision proposed: a second person decides it')
      onClose()
    },
    onError: (error) => toastError(error, 'Not proposed'),
  })
  return (
    <Modal opened onClose={onClose} title={<Text fw={600}>Propose a retention decision</Text>} size="lg">
      <Stack gap="sm">
        <Select label="Decision" data={governance.actions.map((a) => ({ value: a.code, label: a.label }))} value={action} onChange={setAction} allowDeselect={false} />
        {action === 'retain' && (
          <TextInput type="date" label="Review again on" value={reviewOn} onChange={(e) => setReviewOn(e.currentTarget.value)} min={today} required />
        )}
        {action === 'transfer' && <TextInput label="Transferred to" value={transferTo} onChange={(e) => setTransferTo(e.currentTarget.value)} maxLength={300} required />}
        <Textarea label="Reason" description="At least 10 characters." value={reason} onChange={(e) => setReason(e.currentTarget.value)} autosize minRows={2} required />
        {governance.on_hold && action !== 'retain' && (
          <Alert color="orange" variant="light" p="xs">
            The case is under a legal hold: only a decision to retain it can be proposed.
          </Alert>
        )}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={reason.trim().length < 10} loading={propose.isPending} onClick={() => propose.mutate()}>
            Propose
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}
