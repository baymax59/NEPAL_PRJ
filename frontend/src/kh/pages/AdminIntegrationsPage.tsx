// Administration: integration sources (phase CM-6). The outside systems allowed to add findings to cases, each with a
// fixed access policy and a key that is shown once. Disabling a source stops its key at once; what it added stays.

import { Alert, Badge, Button, Code, Group, Modal, MultiSelect, Paper, Select, SimpleGrid, Stack, Text, Textarea, TextInput, Timeline } from '@mantine/core'
import { IconFlask, IconKey, IconPlugConnected, IconPlus } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { kh } from '../api'
import { toastDone, toastError } from '../feedback'
import { CLASSIFICATIONS, humanize } from '../labels'
import { formatWhen } from '../time'
import type { IntegrationSourceOut, SourceKeyIssued } from '../types'
import { ClassificationBadge, ConfirmModal, Copy, EmptyState, Loaded, PageHeader, Panel, PersonName, When } from '../ui'

const KINDS = [
  { value: 'log_analyzer', label: 'Log Analyzer' },
  { value: 'alerting', label: 'Alerting' },
  { value: 'telecom', label: 'CDR / IPDR analysis' },
  { value: 'osint', label: 'OSINT' },
  { value: 'threat_intel', label: 'Threat intelligence' },
  { value: 'forensic_lab', label: 'Forensic laboratory' },
  { value: 'other', label: 'Other' },
]
const EVENTS: Record<string, string> = { registered: 'Registered', disabled: 'Disabled', enabled: 'Enabled again', key_rotated: 'New key issued' }

export function AdminIntegrationsPage() {
  const client = useQueryClient()
  const sources = useQuery({ queryKey: ['kh', 'admin', 'integration-sources'], queryFn: () => kh.integrationSources() })
  const contract = useQuery({ queryKey: ['kh', 'integration-contract'], queryFn: () => kh.integrationContract() })
  const [registering, setRegistering] = useState(false)
  const [issued, setIssued] = useState<SourceKeyIssued | null>(null)
  const refresh = () => client.invalidateQueries({ queryKey: ['kh', 'admin', 'integration-sources'] })
  const testSource = useMutation({
    mutationFn: () => kh.registerTestSource(),
    onSuccess: (result) => {
      refresh()
      client.invalidateQueries({ queryKey: ['kh', 'test-source'] })
      setIssued(result)
    },
    onError: (error) => toastError(error, 'Not registered'),
  })
  const hasTestSource = sources.data?.some((s) => s.fictional)
  const labels = Object.fromEntries((contract.data?.item_types ?? []).map((t) => [t.code, t.label]))
  return (
    <Stack gap="md">
      <PageHeader
        eyebrow="Administration"
        title="Integration sources"
        actions={
          <Group gap="xs">
            {sources.data && !hasTestSource && (
              <Button variant="light" color="yellow" leftSection={<IconFlask size={16} />} loading={testSource.isPending} onClick={() => testSource.mutate()}>
                Add the fictional test source
              </Button>
            )}
            <Button leftSection={<IconPlus size={16} />} onClick={() => setRegistering(true)}>
              Register a source
            </Button>
          </Group>
        }
      >
        <Text size="sm" c="dimmed" maw={820}>
          The systems allowed to add findings to cases: the Log Analyzer, CDR and IPDR analysis, OSINT, alerting. Each sends its key with every
          finding, and the person it adds the finding for must be allowed to add files to the case. A source's policy can't be changed: register a new
          source for a new policy, so every import names the policy it was accepted under.
        </Text>
      </PageHeader>

      <Loaded query={sources}>
        {(list) =>
          list.length === 0 ? (
            <Panel>
              <EmptyState title="No integration source yet" icon={<IconPlugConnected size={22} />}>
                Register each system that will add findings to cases. Until the real systems exist, the fictional test source can stand in for them.
              </EmptyState>
            </Panel>
          ) : (
            <Stack gap="sm">
              {list.map((source) => (
                <SourceCard key={source.id} source={source} labels={labels} onChanged={refresh} onKey={setIssued} />
              ))}
            </Stack>
          )
        }
      </Loaded>

      <Panel title="How a system connects (the integration contract)">
        <Stack gap={6}>
          <Text size="sm">
            <Code>POST /api/v1/integrations/add-to-case</Code> with the person's login (<Code>Authorization: Bearer …</Code>) and the source's key (
            <Code>X-Integration-Key: khi_…</Code>). Each finding has an item type, the record's ID in the source, a summary, the legal
            authority where the source's policy requires it, when it happened, identifiers and the derived result. Raw data stays in the source.
          </Text>
          {contract.data && (
            <Group gap={4}>
              <Text size="xs" c="dimmed">
                Version {contract.data.version}. Item types:
              </Text>
              {contract.data.item_types.map((t) => (
                <Badge key={t.code} size="xs" variant="outline" color="gray" tt="none">
                  {t.label}
                </Badge>
              ))}
            </Group>
          )}
          <Text size="xs" c="dimmed">
            The full contract, with examples, is in docs/case-management/09-integration-contract.md.
          </Text>
        </Stack>
      </Panel>

      {registering && (
        <RegisterSourceModal
          itemTypes={contract.data?.item_types.map((t) => ({ value: t.code, label: t.label })) ?? []}
          onClose={() => setRegistering(false)}
          onRegistered={(result) => {
            setRegistering(false)
            refresh()
            setIssued(result)
          }}
        />
      )}
      {issued && <KeyModal issued={issued} onClose={() => setIssued(null)} />}
    </Stack>
  )
}

function SourceCard({
  source,
  labels,
  onChanged,
  onKey,
}: {
  source: IntegrationSourceOut
  labels: Record<string, string>
  onChanged: () => void
  onKey: (issued: SourceKeyIssued) => void
}) {
  const [action, setAction] = useState<'status' | 'key' | null>(null)
  const enabled = source.status === 'enabled'
  const status = useMutation({
    mutationFn: (reason: string) => kh.changeSourceStatus(source.id, !enabled, reason),
    onSuccess: () => {
      setAction(null)
      onChanged()
      toastDone(`${source.name} ${enabled ? 'disabled: its key no longer works' : 'enabled again'}`)
    },
    onError: (error) => toastError(error),
  })
  const rotate = useMutation({
    mutationFn: (reason: string) => kh.rotateSourceKey(source.id, reason),
    onSuccess: (result) => {
      setAction(null)
      onChanged()
      onKey(result)
    },
    onError: (error) => toastError(error),
  })
  return (
    <Paper withBorder p="md" radius="md" style={{ opacity: enabled ? 1 : 0.75 }}>
      <Stack gap="sm">
        <Group justify="space-between" align="flex-start" wrap="wrap">
          <Stack gap={2}>
            <Group gap={6}>
              <Text fw={700}>{source.name}</Text>
              <Badge color={enabled ? 'teal' : 'gray'} variant="light" size="sm">
                {source.status}
              </Badge>
              {source.fictional && (
                <Badge color="yellow" variant="light" size="sm">
                  fictional test source
                </Badge>
              )}
            </Group>
            <Text size="xs" c="dimmed">
              <Code>{source.code}</Code> · {source.kind_label} · registered by {source.created_by?.display_name ?? '—'} on {formatWhen(source.created_at)}
            </Text>
          </Stack>
          <Group gap="xs">
            <Button size="xs" variant="default" leftSection={<IconKey size={14} />} onClick={() => setAction('key')}>
              Issue a new key
            </Button>
            <Button size="xs" variant="light" color={enabled ? 'red' : 'teal'} onClick={() => setAction('status')}>
              {enabled ? 'Disable' : 'Enable'}
            </Button>
          </Group>
        </Group>
        {source.description && <Text size="sm">{source.description}</Text>}
        <SimpleGrid cols={{ base: 1, md: 3 }} spacing="sm">
          <Stack gap={4}>
            <Text size="xs" c="dimmed">
              May add
            </Text>
            <Group gap={4}>
              {source.policy.allowed_item_types.map((t) => (
                <Badge key={t} size="xs" variant="outline" tt="none">
                  {labels[t] ?? humanize(t)}
                  {source.policy.authority_required_for.includes(t) ? ' (with legal authority)' : ''}
                </Badge>
              ))}
            </Group>
          </Stack>
          <Stack gap={4}>
            <Text size="xs" c="dimmed">
              Only to cases classified at least
            </Text>
            <ClassificationBadge value={source.policy.min_case_classification} />
          </Stack>
          <Stack gap={4}>
            <Text size="xs" c="dimmed">
              Key and use
            </Text>
            <Text size="sm">
              <Code>{source.key_prefix}…</Code> issued {formatWhen(source.key_issued_at)}
            </Text>
            <Text size="xs" c="dimmed">
              {source.imports} finding{source.imports === 1 ? '' : 's'} in {source.cases} case{source.cases === 1 ? '' : 's'}
              {source.last_import_at ? `, the latest ${formatWhen(source.last_import_at)}` : ''}
            </Text>
          </Stack>
        </SimpleGrid>
        <Text size="xs" c="dimmed">
          <b>Legal basis:</b> {source.policy.legal_basis}
        </Text>
        <Timeline bulletSize={12} lineWidth={2} active={source.history.length}>
          {source.history.map((h, i) => (
            <Timeline.Item key={i} title={<Text size="xs" fw={600}>{EVENTS[h.event_type] ?? humanize(h.event_type)}</Text>}>
              <Group gap={6}>
                <PersonName person={h.by} size="xs" />
                <When at={h.at} size="xs" />
                {h.key_prefix && <Code fz="xs">{h.key_prefix}…</Code>}
              </Group>
              {h.reason && h.event_type !== 'registered' && (
                <Text size="xs" c="dimmed">
                  {h.reason}
                </Text>
              )}
            </Timeline.Item>
          ))}
        </Timeline>
      </Stack>
      <ConfirmModal
        opened={action === 'status'}
        onClose={() => setAction(null)}
        title={enabled ? `Disable ${source.name}?` : `Enable ${source.name} again?`}
        confirmLabel={enabled ? 'Disable' : 'Enable'}
        color={enabled ? 'red' : 'teal'}
        reason="required"
        loading={status.isPending}
        onConfirm={(reason) => status.mutate(reason)}
      >
        <Text size="sm">
          {enabled
            ? 'Its key stops working at once. The findings it already added stay in the cases, with their history.'
            : 'Its current key works again.'}
        </Text>
      </ConfirmModal>
      <ConfirmModal
        opened={action === 'key'}
        onClose={() => setAction(null)}
        title={`Issue a new key for ${source.name}?`}
        confirmLabel="Issue a new key"
        reason="required"
        loading={rotate.isPending}
        onConfirm={(reason) => rotate.mutate(reason)}
      >
        <Text size="sm">The current key ({source.key_prefix}…) stops working at once. The new key is shown once.</Text>
      </ConfirmModal>
    </Paper>
  )
}

function RegisterSourceModal({ itemTypes, onClose, onRegistered }: { itemTypes: { value: string; label: string }[]; onClose: () => void; onRegistered: (r: SourceKeyIssued) => void }) {
  const [code, setCode] = useState('')
  const [name, setName] = useState('')
  const [kind, setKind] = useState<string | null>('log_analyzer')
  const [legalBasis, setLegalBasis] = useState('')
  const [allowed, setAllowed] = useState<string[]>([])
  const [authority, setAuthority] = useState<string[] | null>(null)
  const [minimum, setMinimum] = useState<string | null>('internal')
  const [description, setDescription] = useState('')
  const required = authority ?? allowed.filter((t) => t === 'cdr_result' || t === 'ipdr_result')
  const register = useMutation({
    mutationFn: () =>
      kh.registerSource({
        code: code.trim(),
        name: name.trim(),
        kind: kind ?? 'other',
        legal_basis: legalBasis.trim(),
        allowed_item_types: allowed,
        authority_required_for: required,
        min_case_classification: (minimum ?? 'internal') as 'internal',
        description: description.trim() || null,
      }),
    onSuccess: onRegistered,
    onError: (error) => toastError(error, 'Not registered'),
  })
  const ready = /^[a-z0-9][a-z0-9-]{1,62}$/.test(code.trim()) && name.trim().length >= 3 && legalBasis.trim().length >= 10 && allowed.length > 0
  return (
    <Modal opened onClose={onClose} size="lg" title={<Text fw={600}>Register an integration source</Text>}>
      <Stack gap="sm">
        <Group grow align="flex-start">
          <TextInput label="Code" description="Lower-case letters, digits and '-'; part of the findings' paths" value={code} onChange={(e) => setCode(e.currentTarget.value.toLowerCase())} required />
          <Select label="Kind of system" data={KINDS} value={kind} onChange={setKind} allowDeselect={false} />
        </Group>
        <TextInput label="Name" value={name} onChange={(e) => setName(e.currentTarget.value)} required />
        <Textarea
          label="Legal basis"
          description="Under what authority this system's data is obtained (at least 10 characters). It is shown with every finding it adds."
          value={legalBasis}
          onChange={(e) => setLegalBasis(e.currentTarget.value)}
          autosize
          minRows={2}
          required
        />
        <MultiSelect label="May add" data={itemTypes} value={allowed} onChange={setAllowed} required placeholder="Kinds of finding" />
        <MultiSelect
          label="Legal authority reference required for"
          description="A requisition or order number must come with these findings. CDR and IPDR results by default."
          data={itemTypes.filter((t) => allowed.includes(t.value))}
          value={required.filter((t) => allowed.includes(t))}
          onChange={setAuthority}
        />
        <Select
          label="Only to cases classified at least"
          description="Findings of this source never go to a less protected case."
          data={CLASSIFICATIONS.map((c) => ({ value: c, label: humanize(c) }))}
          value={minimum}
          onChange={setMinimum}
          allowDeselect={false}
        />
        <Textarea label="Description (optional)" value={description} onChange={(e) => setDescription(e.currentTarget.value)} autosize minRows={2} />
        <Alert color="gray" variant="light">
          The policy can't be changed later. The key is shown once, after registering.
        </Alert>
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={!ready} loading={register.isPending} onClick={() => register.mutate()}>
            Register
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}

function KeyModal({ issued, onClose }: { issued: SourceKeyIssued; onClose: () => void }) {
  return (
    <Modal opened onClose={onClose} size="lg" title={<Text fw={600}>The key of {issued.source.name}</Text>} closeOnClickOutside={false}>
      <Stack gap="sm">
        <Alert color="orange" variant="light" icon={<IconKey size={18} />}>
          {issued.key_note}
        </Alert>
        <Group gap={6} wrap="nowrap">
          <Code block style={{ flex: 1, wordBreak: 'break-all' }}>
            {issued.key}
          </Code>
          <Copy value={issued.key} />
        </Group>
        <Group justify="flex-end">
          <Button onClick={onClose}>I have copied it</Button>
        </Group>
      </Stack>
    </Modal>
  )
}
