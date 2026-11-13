// New case registration (spec §6, §21 screen 5): one form creates the case, its permanent folders (from the type of case)
// and puts the lead investigator on its team.

import { Alert, Autocomplete, Badge, Button, Checkbox, Divider, Group, Modal, Paper, SegmentedControl, Select, SimpleGrid, Stack, Text, TextInput, ThemeIcon, Timeline } from '@mantine/core'
import { IconCheck, IconFolder, IconInfoCircle, IconMail, IconPencil, IconUsers } from '@tabler/icons-react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router'
import { useAuth } from '../../auth/useAuth'
import { kh } from '../api'
import { CLASSIFICATIONS, humanize } from '../labels'
import { ColleagueSelect } from '../pickers'
import { plainToHtml } from '../plainToHtml'
import { RichTextEditor } from '../RichText'
import type { CaseCreated, Colleague } from '../types'
import { PageHeader, Panel } from '../ui'
import { toastError, useOnceKey } from '../feedback'

const REF_TYPES = ['FIR', 'Complaint', 'General diary entry', 'Court case', 'Notice', 'Other']

const MIN_DESCRIPTION = 10
const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/

type Written = { text: string; html: string }

/** The text and buttons of the compose window. It is mounted each time the window opens, so it always starts from the saved description. */
function ComposeBody({ value, onSave, onClose, caseTitle, typeLabel }: { value: Written; onSave: (written: Written) => void; onClose: () => void; caseTitle: string; typeLabel: string }) {
  const [draft, setDraft] = useState<Written>(value)
  const [initial] = useState(() => value.html || plainToHtml(value.text))
  return (
    <>
      <Group px="md" py={8} gap="sm" wrap="nowrap">
        <Text size="sm" c="dimmed" w={48}>
          Case
        </Text>
        <Text size="sm" truncate>
          {caseTitle || 'No title yet'}
        </Text>
      </Group>
      <Divider />
      <Group px="md" py={8} gap="sm" wrap="nowrap">
        <Text size="sm" c="dimmed" w={48}>
          Type
        </Text>
        <Text size="sm" truncate>
          {typeLabel || 'Not chosen yet'}
        </Text>
      </Group>
      <Divider />
      <RichTextEditor initial={initial} onChange={(html, text) => setDraft({ html, text })} />
      <Divider />
      <Group justify="space-between" px="md" py="sm">
        <Group gap="xs">
          <Button size="sm" disabled={draft.text.trim().length < MIN_DESCRIPTION} onClick={() => onSave({ html: draft.html, text: draft.text.trim() })}>
            Save
          </Button>
          <Button size="sm" variant="subtle" color="gray" onClick={onClose}>
            Discard
          </Button>
        </Group>
        <Text size="xs" c="dimmed">
          {draft.text.trim().length} characters
        </Text>
      </Group>
    </>
  )
}

/** The description of the case, written in a small compose window like an email: Save keeps the text, Discard (or closing) drops the changes. */
function DescriptionComposer({ opened, onClose, ...body }: { opened: boolean; onClose: () => void; value: Written; onSave: (written: Written) => void; caseTitle: string; typeLabel: string }) {
  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title={
        <Group gap={8}>
          <IconMail size={18} />
          <Text fw={600} size="sm">
            Description of the case
          </Text>
        </Group>
      }
      size={680}
      padding={0}
      radius="md"
      centered
      overlayProps={{ backgroundOpacity: 0.35, blur: 2 }}
      styles={{
        header: { background: 'var(--mantine-color-default-hover)', borderBottom: '1px solid var(--mantine-color-default-border)', minHeight: 44, padding: '0 12px 0 16px' },
        body: { padding: 0 },
      }}
    >
      <ComposeBody {...body} onClose={onClose} />
    </Modal>
  )
}

export function RegisterCasePage() {
  const { user } = useAuth()
  const [key, renew] = useOnceKey()
  const types = useQuery({ queryKey: ['kh', 'case-types'], queryFn: () => kh.caseTypes(), staleTime: Infinity })
  const allowed = CLASSIFICATIONS.slice(0, CLASSIFICATIONS.indexOf(user?.clearance ?? 'internal') + 1)
  const [title, setTitle] = useState('')
  const [caseType, setCaseType] = useState<string | null>(null)
  const [description, setDescription] = useState('')
  const [descriptionHtml, setDescriptionHtml] = useState('')
  const [composing, setComposing] = useState(false)
  const [repUnknown, setRepUnknown] = useState(false)
  const [repName, setRepName] = useState('')
  const [repPhone, setRepPhone] = useState('')
  const [repEmail, setRepEmail] = useState('')
  const [repAddress, setRepAddress] = useState('')
  const [priority, setPriority] = useState('medium')
  const [classification, setClassification] = useState<string>(allowed.includes('restricted') ? 'restricted' : (allowed[allowed.length - 1] ?? 'internal'))
  const [jurisdiction, setJurisdiction] = useState('')
  const [lead, setLead] = useState<Colleague | null>(null)
  const stations = useQuery({ queryKey: ['kh', 'stations'], queryFn: () => kh.stations(), staleTime: 60_000 })
  const [stationChoice, setStationChoice] = useState<string | null>(null)
  const [supervisor, setSupervisor] = useState<Colleague | null>(null)
  const [refType, setRefType] = useState('FIR')
  const [refNumber, setRefNumber] = useState('')
  const [refAuthority, setRefAuthority] = useState('')
  const [refDate, setRefDate] = useState('')
  const [created, setCreated] = useState<CaseCreated | null>(null)
  const chosen = types.data?.find((t) => t.code === caseType)
  const mutation = useMutation({
    mutationFn: () =>
      kh.createCase(
        {
          title: title.trim(),
          case_type: caseType!,
          description: description.trim(),
          description_html: descriptionHtml || null,
          reported_by: repUnknown
            ? { unknown: true }
            : [repName, repPhone, repEmail, repAddress].some((v) => v.trim())
              ? { unknown: false, name: repName.trim() || null, phone: repPhone.trim() || null, email: repEmail.trim() || null, address: repAddress.trim() || null }
              : null,
          priority: priority as 'medium',
          classification: classification as 'restricted',
          jurisdiction: jurisdiction.trim() || null,
          station_id: stationId,
          lead_investigator_id: lead?.id ?? null,
          supervisor_id: supervisor?.id ?? null,
          official_reference: refNumber.trim()
            ? { ref_type: refType.trim() || 'FIR', number: refNumber.trim(), issuing_authority: refAuthority.trim() || null, ref_date: refDate || null, source: 'manual' }
            : null,
        },
        key,
      ),
    onSuccess: (result) => {
      renew()
      setCreated(result)
    },
    onError: (error) => toastError(error, 'The case was not registered'),
  })

  if (created) {
    return (
      <Stack gap="md" maw={760}>
        <PageHeader eyebrow="Case registered" title={created.display_id} />
        <Paper withBorder p="lg">
          <Timeline active={3} bulletSize={26} lineWidth={2}>
            <Timeline.Item bullet={<IconCheck size={14} />} title="Case registered">
              <Text size="sm" c="dimmed">
                {created.display_id}: the permanent identity of the case. It is never deleted.
              </Text>
            </Timeline.Item>
            <Timeline.Item bullet={<IconFolder size={14} />} title={`${created.folders.length} folders made for you`}>
              <Group gap={4} mt={4}>
                {created.folders.map((f) => (
                  <Badge key={f} size="xs" variant="outline" color="gray" tt="none" ff="monospace">
                    {f}
                  </Badge>
                ))}
              </Group>
              <Text size="sm" c="dimmed" mt={4}>
                The Investigator or Supervisor can add more folders later. Folders are permanent.
              </Text>
            </Timeline.Item>
            <Timeline.Item bullet={<IconUsers size={14} />} title={`${created.lead.display_name} leads the case`}>
              <Text size="sm" c="dimmed">
                The Investigator can now add Sub Investigators and Analysts to the team; they join at once.
              </Text>
            </Timeline.Item>
            <Timeline.Item bullet={<IconCheck size={14} />} title="Recorded in the history and the audit trail" />
          </Timeline>
          <Group mt="lg">
            <Button component={Link} to={`/kh/case/${created.case_id}`}>
              Open {created.display_id}
            </Button>
            <Button variant="subtle" onClick={() => setCreated(null)}>
              Register another case
            </Button>
          </Group>
        </Paper>
      </Stack>
    )
  }

  // One station: it is used without asking. Several (an Administrator, a Super Admin): the person chooses.
  const several = (stations.data?.length ?? 0) > 1
  const stationId = several ? stationChoice : (stations.data?.[0]?.id ?? null)
  const emailBad = !repUnknown && repEmail.trim() !== '' && !EMAIL.test(repEmail.trim())
  const ready = !emailBad && title.trim().length >= 3 && caseType && description.trim().length >= MIN_DESCRIPTION && (!several || Boolean(stationChoice))
  return (
    <Stack gap="md" maw={980}>
      <PageHeader eyebrow="Investigation" title="Register a case" />
      <Panel title="The case">
        <Stack gap="sm">
          {several && (
            <Select
              label="Police station"
              description="The station that owns the case. Its people and supervisors are the ones you can choose below."
              data={(stations.data ?? []).map((st) => ({ value: st.id, label: `${st.code}: ${st.name}` }))}
              value={stationChoice}
              onChange={(value) => {
                setStationChoice(value)
                setLead(null)
                setSupervisor(null)
              }}
              required
            />
          )}
          <TextInput label="Title" value={title} onChange={(e) => setTitle(e.currentTarget.value)} required maxLength={300} placeholder="e.g. Online banking fraud (fictional)" />
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <Select
              label="Type of case"
              data={(types.data ?? []).map((t) => ({ value: t.code, label: t.label }))}
              value={caseType}
              onChange={setCaseType}
              searchable
              required
            />
            <TextInput label="Jurisdiction" value={jurisdiction} onChange={(e) => setJurisdiction(e.currentTarget.value)} placeholder="e.g. Example Nagar police station (fictional)" />
          </SimpleGrid>
          {chosen && (
            <Paper withBorder p="xs" bg="var(--mantine-color-default-hover)">
              <Text size="xs" c="dimmed" mb={4}>
                Folders made for the case
              </Text>
              <Group gap={4}>
                {chosen.folders.map((f) => (
                  <Badge key={f} size="xs" variant="outline" color="gray" tt="none" ff="monospace">
                    {f}
                  </Badge>
                ))}
              </Group>
            </Paper>
          )}
          <div>
            <Button
              variant="default"
              fullWidth
              justify="space-between"
              leftSection={<IconPencil size={16} />}
              rightSection={description.trim().length >= MIN_DESCRIPTION ? <IconCheck size={16} color="var(--mantine-color-teal-6)" /> : <span style={{ color: 'var(--mantine-color-error)' }}>*</span>}
              onClick={() => setComposing(true)}
            >
              Description
            </Button>
            {description.trim() && (
              <Text size="xs" c="dimmed" mt={4} lineClamp={2}>
                {description.trim()}
              </Text>
            )}
          </div>
          <DescriptionComposer opened={composing} onClose={() => setComposing(false)} value={{ text: description, html: descriptionHtml }} caseTitle={title.trim()} typeLabel={chosen?.label ?? ''} onSave={(written) => { setDescription(written.text); setDescriptionHtml(written.html); setComposing(false) }} />
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <div>
              <Text size="sm" fw={500} mb={4}>
                Priority
              </Text>
              <SegmentedControl fullWidth value={priority} onChange={setPriority} data={['low', 'medium', 'high', 'critical'].map((p) => ({ value: p, label: humanize(p) }))} />
            </div>
            <Select
              label="Classification"
              data={allowed.map((c) => ({ value: c, label: humanize(c) }))}
              value={classification}
              onChange={(v) => {
                if (!v) return
                setClassification(v)
                setLead(null)
                setSupervisor(null)
              }}
              allowDeselect={false}
            />
          </SimpleGrid>
        </Stack>
      </Panel>
      <Panel title="People">
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <ColleagueSelect purpose="lead" classification={classification} stationId={stationId ?? undefined} label="Lead investigator" value={lead} onChange={setLead} />
          <ColleagueSelect purpose="supervisor" classification={classification} stationId={stationId ?? undefined} label="Supervisor (recommended)" value={supervisor} onChange={setSupervisor} />
        </SimpleGrid>
      </Panel>
      <Panel title="Reported by">
        <Stack gap="sm">
          <Checkbox
            label="Unknown"
            checked={repUnknown}
            onChange={(e) => {
              setRepUnknown(e.currentTarget.checked)
              if (e.currentTarget.checked) {
                setRepName('')
                setRepPhone('')
                setRepEmail('')
                setRepAddress('')
              }
            }}
          />
          <SimpleGrid cols={{ base: 1, sm: 3 }}>
            <TextInput label="Name" value={repName} onChange={(e) => setRepName(e.currentTarget.value)} disabled={repUnknown} maxLength={200} />
            <TextInput label="Phone" value={repPhone} onChange={(e) => setRepPhone(e.currentTarget.value)} disabled={repUnknown} maxLength={40} />
            <TextInput label="Email" value={repEmail} onChange={(e) => setRepEmail(e.currentTarget.value)} disabled={repUnknown} maxLength={200} error={emailBad ? 'Not a valid email address' : undefined} />
          </SimpleGrid>
          <TextInput label="Address" value={repAddress} onChange={(e) => setRepAddress(e.currentTarget.value)} disabled={repUnknown} maxLength={500} />
        </Stack>
      </Panel>
      <Panel title="Official reference (optional)">
        <SimpleGrid cols={{ base: 1, sm: 4 }}>
          <Autocomplete label="Kind" data={REF_TYPES} value={refType} onChange={setRefType} />
          <TextInput label="Number" value={refNumber} onChange={(e) => setRefNumber(e.currentTarget.value)} placeholder="e.g. 0123/2026" />
          <TextInput label="Issued by" value={refAuthority} onChange={(e) => setRefAuthority(e.currentTarget.value)} />
          <TextInput label="Date" type="date" value={refDate} onChange={(e) => setRefDate(e.currentTarget.value)} />
        </SimpleGrid>
      </Panel>
      <Alert color="gray" variant="light" icon={<IconInfoCircle size={18} />}>
        Registering creates the permanent case, its folders and its first history entry, and puts the lead on the team.
        Nothing about it can be deleted later; corrections are new versions.
      </Alert>
      <Group justify="flex-end">
        <Button size="md" disabled={!ready} loading={mutation.isPending} onClick={() => mutation.mutate()} leftSection={<ThemeIcon size="sm" variant="transparent" c="inherit"><IconCheck size={16} /></ThemeIcon>}>
          Register the case
        </Button>
      </Group>
    </Stack>
  )
}
