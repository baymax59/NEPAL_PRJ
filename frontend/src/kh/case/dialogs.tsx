// The case's dialogs: add an exhibit, write or revise a note, add a folder, add a team member, hand the case over.
// Each write carries an Idempotency-Key, and a revision names the version it was based on, so a double click or a
// colleague's simultaneous change can't make a mess.

import { Alert, Badge, Button, Group, Modal, Select, SimpleGrid, Stack, Text, TextInput, Textarea } from '@mantine/core'
import { Dropzone } from '@mantine/dropzone'
import { IconAlertTriangle, IconCloudUpload, IconFile, IconInfoCircle } from '@tabler/icons-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { formatBytes } from '../../lib/format'
import { kh } from '../api'
import { toastDone, toastError, useOnceKey } from '../feedback'
import { ARTIFACT_TYPES, CLASSIFICATIONS, humanize, roleLabel } from '../labels'
import { ColleagueSelect } from '../pickers'
import type { CaseDetail, Colleague } from '../types'
import { folderNameProblem, useCaseType, useRefreshCase, withOffset } from './helpers'

const folderNames = (detail: CaseDetail) => detail.folders.map((f) => f.name)

// ------------------------------------------------------------------ add an exhibit

export function AddEvidenceDialog({
  opened,
  onClose,
  detail,
  folder: initialFolder,
  onAdded,
}: {
  opened: boolean
  onClose: () => void
  detail: CaseDetail
  folder?: string
  /** Called with the folder the exhibit went into (the Files tab opens it). */
  onAdded?: (folder: string) => void
}) {
  const refresh = useRefreshCase(detail.id)
  const caseType = useCaseType(detail)
  const [key, renew] = useOnceKey()
  const folders = folderNames(detail)
  const [file, setFile] = useState<File | null>(null)
  const [folder, setFolder] = useState(initialFolder ?? folders.find((f) => f.includes('evidence')) ?? folders[0] ?? 'case-information')
  const [title, setTitle] = useState('')
  const [type, setType] = useState<string | null>(null)
  const [description, setDescription] = useState('')
  const [classification, setClassification] = useState<string | null>(null)
  const [source, setSource] = useState('')
  const [collectedAt, setCollectedAt] = useState('')
  const [collectedBy, setCollectedBy] = useState('')
  const [authority, setAuthority] = useState('')
  const mutation = useMutation({
    mutationFn: () => {
      if (!file) throw new Error('Choose a file')
      const form = new FormData()
      const fields: Record<string, string | null> = {
        folder,
        title: title.trim() || file.name,
        evidence_type: type,
        description: description.trim() || null,
        classification,
        source: source.trim() || null,
        collected_at: withOffset(collectedAt),
        collected_by: collectedBy.trim() || null,
        collection_authority: authority.trim() || null,
      }
      for (const [name, value] of Object.entries(fields)) if (value) form.append(name, value)
      form.append('file', file)
      return kh.addEvidence(detail.id, form, key)
    },
    onSuccess: (added) => {
      renew()
      refresh()
      const duplicate = added.duplicates.length ? ` The same file is also ${added.duplicates.map((d) => d.display_id).join(', ')}.` : ''
      toastDone(`${added.evidence.display_id} added to the case.${duplicate}`)
      setFile(null)
      setTitle('')
      onAdded?.(folder)
      onClose()
    },
    onError: (error) => toastError(error, 'The exhibit was not added'),
  })
  return (
    <Modal opened={opened} onClose={onClose} size="xl" title={<Text fw={600}>Add an exhibit</Text>}>
      <Stack gap="sm">
        <Dropzone onDrop={(files) => setFile(files[0] ?? null)} multiple={false} maxSize={100 * 1024 * 1024} onReject={() => toastError(new Error('The file is larger than 100 MB'))}>
          <Group justify="center" gap="md" mih={90} style={{ pointerEvents: 'none' }}>
            {file ? <IconFile size={34} stroke={1.4} /> : <IconCloudUpload size={34} stroke={1.4} />}
            <div>
              <Text size="sm" fw={500}>
                {file ? file.name : 'Drop the file here, or click to choose it'}
              </Text>
              <Text size="xs" c="dimmed">
                {file ? formatBytes(file.size) : 'Up to 100 MB. The file is stored once and never changed; its originality is checked automatically.'}
              </Text>
            </div>
          </Group>
        </Dropzone>
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <Select label="Folder" data={folders} value={folder} onChange={(v) => v && setFolder(v)} searchable allowDeselect={false} />
          <Select
            label="Type of exhibit"
            data={(caseType?.evidence_types ?? []).map((t) => ({ value: t, label: humanize(t) }))}
            value={type}
            onChange={setType}
            clearable
            searchable
          />
        </SimpleGrid>
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <TextInput label="Title" placeholder={file?.name ?? 'e.g. Bank statement, March'} value={title} onChange={(e) => setTitle(e.currentTarget.value)} maxLength={300} />
          <Select label="Classification" data={CLASSIFICATIONS.map((c) => ({ value: c, label: humanize(c) }))} value={classification} onChange={setClassification} clearable />
        </SimpleGrid>
        <Textarea label="Description" value={description} onChange={(e) => setDescription(e.currentTarget.value)} autosize minRows={2} />
        <Text size="xs" fw={600} c="dimmed" tt="uppercase" mt={4}>
          Provenance (where it came from)
        </Text>
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <TextInput label="Source" placeholder="e.g. Complainant's phone, bank's reply to notice" value={source} onChange={(e) => setSource(e.currentTarget.value)} />
          <TextInput label="Collected at" type="datetime-local" description="Your computer's time zone is recorded with it" value={collectedAt} onChange={(e) => setCollectedAt(e.currentTarget.value)} />
          <TextInput label="Collected by" value={collectedBy} onChange={(e) => setCollectedBy(e.currentTarget.value)} />
          <TextInput label="Collection authority" placeholder="e.g. Seizure memo, court order or notice number" value={authority} onChange={(e) => setAuthority(e.currentTarget.value)} />
        </SimpleGrid>
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={!file} loading={mutation.isPending} onClick={() => mutation.mutate()} leftSection={<IconCloudUpload size={16} />}>
            Add to the case
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}

// ------------------------------------------------------------------ notes and analyses (write or revise)

export function NoteDialog({
  opened,
  onClose,
  detail,
  revise,
  folder: initialFolder,
  onAdded,
}: {
  opened: boolean
  onClose: () => void
  detail: CaseDetail
  folder?: string
  /** A new version of a note: the version it is based on, so that a colleague's change is never overwritten. */
  revise?: { artifactId: string; title: string; text: string; version: number }
  /** Called with the folder of the new note (the Files tab opens it). */
  onAdded?: (folder: string) => void
}) {
  const refresh = useRefreshCase(detail.id)
  const [key, renew] = useOnceKey()
  const folders = folderNames(detail)
  const [folder, setFolder] = useState(initialFolder ?? folders.find((f) => f.includes('notes')) ?? folders[0] ?? 'case-information')
  const [title, setTitle] = useState('')
  const [type, setType] = useState('note')
  const [text, setText] = useState(revise?.text ?? '')
  const [changeNote, setChangeNote] = useState('')
  const mutation = useMutation({
    mutationFn: async () => {
      if (revise) {
        await kh.reviseNote(revise.artifactId, { content: { text }, expected_version: revise.version, note: changeNote.trim() || null }, key)
        return folder
      }
      await kh.addNote(detail.id, { folder, artifact_type: type as 'note', title: title.trim(), content: { text }, note: changeNote.trim() || null }, key)
      return folder
    },
    onSuccess: (where) => {
      renew()
      refresh()
      toastDone(revise ? 'Saved as a new version' : 'Added to the case')
      if (!revise) onAdded?.(where)
      onClose()
    },
    onError: (error) => toastError(error, 'Not saved'),
  })
  return (
    <Modal opened={opened} onClose={onClose} size="xl" title={<Text fw={600}>{revise ? `New version of ${revise.title}` : 'New note or analysis'}</Text>}>
      <Stack gap="sm">
        {revise && (
          <Alert color="gray" variant="light" icon={<IconInfoCircle size={18} />}>
            A new version replaces nothing: the current version stays in the history, word for word.
          </Alert>
        )}
        {!revise && (
          <SimpleGrid cols={{ base: 1, sm: 2 }}>
            <Select label="Folder" data={folders} value={folder} onChange={(v) => v && setFolder(v)} searchable allowDeselect={false} />
            <Select
              label="Kind"
              data={['note', 'analysis', 'transcription', 'timeline'].map((t) => ({ value: t, label: ARTIFACT_TYPES[t] }))}
              value={type}
              onChange={(v) => v && setType(v)}
              allowDeselect={false}
            />
          </SimpleGrid>
        )}
        {!revise && <TextInput label="Title" value={title} onChange={(e) => setTitle(e.currentTarget.value)} maxLength={300} required />}
        <Textarea label="Text" value={text} onChange={(e) => setText(e.currentTarget.value)} autosize minRows={8} maxRows={22} required />
        <TextInput label={revise ? 'What changed' : 'Note (optional)'} value={changeNote} onChange={(e) => setChangeNote(e.currentTarget.value)} maxLength={2000} />
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={!text.trim() || (!revise && !title.trim())} loading={mutation.isPending} onClick={() => mutation.mutate()}>
            {revise ? 'Save new version' : 'Add to the case'}
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}

// ------------------------------------------------------------------ a new folder

export function FolderDialog({ opened, onClose, detail, onAdded }: { opened: boolean; onClose: () => void; detail: CaseDetail; onAdded?: (name: string) => void }) {
  const refresh = useRefreshCase(detail.id)
  const [key, renew] = useOnceKey()
  const [name, setName] = useState('')
  const problem = folderNameProblem(name)
  const exists = detail.folders.some((f) => f.name.toLowerCase() === name.trim().toLowerCase())
  const mutation = useMutation({
    mutationFn: () => kh.addFolder(detail.id, name.trim(), key),
    onSuccess: (folder) => {
      renew()
      refresh()
      toastDone(`Folder ${folder.name} added`)
      onAdded?.(folder.name)
      setName('')
      onClose()
    },
    onError: (error) => toastError(error, 'The folder was not added'),
  })
  return (
    <Modal opened={opened} onClose={onClose} title={<Text fw={600}>New folder</Text>}>
      <Stack gap="sm">
        <TextInput
          label="Folder name"
          placeholder="e.g. bank-letters"
          value={name}
          onChange={(e) => setName(e.currentTarget.value)}
          error={problem ?? (exists ? 'The case already has a folder with this name' : null)}
          maxLength={100}
          data-autofocus
        />
        <Text size="xs" c="dimmed">
          A folder is permanent: it can't be renamed or removed. Folders are flat, with no sub-folders.
        </Text>
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={!name.trim() || problem !== null || exists} loading={mutation.isPending} onClick={() => mutation.mutate()}>
            Add folder
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}

// ------------------------------------------------------------------ add a team member: straight into the case

export function AddMemberDialog({ opened, onClose, detail }: { opened: boolean; onClose: () => void; detail: CaseDetail }) {
  const queryClient = useQueryClient()
  const [person, setPerson] = useState<Colleague | null>(null)
  const [role, setRole] = useState<string | null>(null)
  const roles = person?.roles ?? []
  const mutation = useMutation({
    mutationFn: () => kh.addMember(detail.id, { user_id: person!.id, role: role as 'analyst' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['kh', 'case', detail.id] })
      queryClient.invalidateQueries({ queryKey: ['kh', 'colleagues'] })
      toastDone(`${person?.display_name} is now on the team`)
      setPerson(null)
      setRole(null)
      onClose()
    },
    onError: (error) => toastError(error, 'Not added'),
  })
  return (
    <Modal opened={opened} onClose={onClose} size="lg" title={<Text fw={600}>Add a team member to {detail.display_id}</Text>}>
      <Stack gap="sm">
        <ColleagueSelect
          purpose="team"
          caseId={detail.id}
          label="Colleague"
          description="Only people who work at this case's station, with enough clearance, are listed."
          value={person}
          onChange={(p) => {
            setPerson(p)
            setRole(p?.roles.includes('sub_investigator') ? 'sub_investigator' : (p?.roles[0] ?? null))
          }}
          required
        />
        <Select
          label="Part in the case"
          data={roles.map((r) => ({ value: r, label: roleLabel(r) }))}
          value={role}
          onChange={setRole}
          disabled={!person}
          description="Sub Investigators help the Investigator: they add notes and exhibits. Analysts analyse the data and add their findings. Viewers only read."
          allowDeselect={false}
        />
        <Alert color="gray" variant="light" icon={<IconInfoCircle size={18} />}>
          They join at once and are told by a notice. There is nothing for them to accept and nothing to approve. Every change of the team is kept in the case's history.
        </Alert>
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={!person || !role} loading={mutation.isPending} onClick={() => mutation.mutate()}>
            Add to the team
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}

// ------------------------------------------------------------------ hand the case to another Investigator

export function HandOverDialog({ opened, onClose, detail }: { opened: boolean; onClose: () => void; detail: CaseDetail }) {
  const queryClient = useQueryClient()
  const [person, setPerson] = useState<Colleague | null>(null)
  const [reason, setReason] = useState('')
  const mutation = useMutation({
    mutationFn: () => kh.changeLead(detail.id, person!.id, reason.trim()),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['kh'] })
      toastDone(`${person?.display_name} now leads ${detail.display_id}`)
      setPerson(null)
      setReason('')
      onClose()
    },
    onError: (error) => toastError(error, 'Not handed over'),
  })
  return (
    <Modal opened={opened} onClose={onClose} size="lg" title={<Text fw={600}>Hand {detail.display_id} to another Investigator</Text>}>
      <Stack gap="sm">
        <ColleagueSelect
          purpose="lead"
          classification={detail.classification}
          label="New Investigator"
          description="Only Investigators with enough clearance for this case are listed."
          value={person}
          onChange={setPerson}
          required
        />
        <Textarea label="Reason (kept in the history)" value={reason} onChange={(e) => setReason(e.currentTarget.value)} autosize minRows={2} maxLength={2000} required />
        <Alert color="gray" variant="light" icon={<IconInfoCircle size={18} />}>
          The present Investigator stays on the team as a Sub Investigator unless you remove them afterwards. What they did stays credited to them.
        </Alert>
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={!person || reason.trim().length < 5} loading={mutation.isPending} onClick={() => mutation.mutate()}>
            Hand over
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}

export function ActiveContentWarning() {
  return (
    <Alert color="orange" icon={<IconAlertTriangle size={18} />} p="xs">
      <Text size="xs">
        Active content (a program, script or web page). It is kept as evidence but never opened or previewed here.
      </Text>
    </Alert>
  )
}

export function KindBadge({ kind }: { kind: string }) {
  return kind === 'evidence' ? (
    <Badge size="xs" color="teal" variant="outline">
      exhibit
    </Badge>
  ) : null
}

/** What is wrong with a typed case number (null when fine or still empty): the backend's rule. */
const caseNumberProblem = (value: string): string | null =>
  value.trim() && !/^[A-Za-z0-9][A-Za-z0-9 ./_-]{2,31}$/.test(value.trim().replace(/\s+/g, ' '))
    ? '3 to 32 letters, digits, spaces or . / _ - (starting with a letter or digit)'
    : null

/** Change the case number: for the supervisor or an administrator. The old number is kept and still finds the case. */
export function CaseNameDialog({ opened, onClose, detail }: { opened: boolean; onClose: () => void; detail: CaseDetail }) {
  const client = useQueryClient()
  const [name, setName] = useState('')
  const [reason, setReason] = useState('')
  const same = name.trim() === detail.title
  const mutation = useMutation({
    mutationFn: () => kh.changeCaseName(detail.id, { name: name.trim(), reason: reason.trim() }),
    onSuccess: (updated) => {
      void client.invalidateQueries({ queryKey: ['kh'] })
      toastDone(`Case name updated to "${updated.title}"`)
      setName('')
      setReason('')
      onClose()
    },
    onError: (error) => toastError(error, 'The case name was not changed'),
  })
  return (
    <Modal opened={opened} onClose={onClose} title={<Text fw={600}>Edit case name</Text>}>
      <Stack gap="sm">
        <TextInput label="Current name" value={detail.title} readOnly />
        <TextInput
          label="New case name"
          placeholder="Enter the new case title"
          value={name}
          onChange={(e) => setName(e.currentTarget.value)}
          error={same ? 'This is already the current name' : null}
          maxLength={300}
          data-autofocus
        />
        <Textarea
          label="Reason (recorded in the history)"
          value={reason}
          onChange={(e) => setReason(e.currentTarget.value)}
          autosize
          minRows={2}
          maxLength={1000}
          required
        />
        <Text size="xs" c="dimmed">
          Only the supervisor or administrator may rename a case. The change and the reason are saved
          as a numbered history entry with your name and timestamp.
        </Text>
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>Cancel</Button>
          <Button
            disabled={name.trim().length < 3 || same || reason.trim().length < 5}
            loading={mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            Save name
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}


export function CaseNumberDialog({ opened, onClose, detail }: { opened: boolean; onClose: () => void; detail: CaseDetail }) {
  const client = useQueryClient()
  const [number, setNumber] = useState('')
  const [reason, setReason] = useState('')
  const problem = caseNumberProblem(number)
  const same = number.trim().toUpperCase() === detail.display_id.toUpperCase()
  const mutation = useMutation({
    mutationFn: () => kh.changeCaseNumber(detail.id, { number: number.trim().replace(/\s+/g, ' '), reason: reason.trim() }),
    onSuccess: (updated) => {
      void client.invalidateQueries({ queryKey: ['kh'] })
      toastDone(`The case number is now ${updated.display_id}`)
      setNumber('')
      setReason('')
      onClose()
    },
    onError: (error) => toastError(error, 'The case number was not changed'),
  })
  return (
    <Modal opened={opened} onClose={onClose} title={<Text fw={600}>Change the case number</Text>}>
      <Stack gap="sm">
        <TextInput label="Current number" value={detail.display_id} readOnly />
        <TextInput
          label="New case number"
          placeholder="e.g. PS-CYB-2026/14"
          value={number}
          onChange={(e) => setNumber(e.currentTarget.value)}
          error={problem ?? (same ? 'This is already the number of the case' : null)}
          maxLength={32}
          data-autofocus
        />
        <Textarea label="Reason (kept in the history)" value={reason} onChange={(e) => setReason(e.currentTarget.value)} autosize minRows={2} maxLength={1000} required />
        <Text size="xs" c="dimmed">
          The old number is kept: it still finds the case, it is never given to another case, and the change is a numbered entry of the history with your name and the reason.
          Reports already made keep the number they were made with.
        </Text>
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={!number.trim() || problem !== null || same || reason.trim().length < 5} loading={mutation.isPending} onClick={() => mutation.mutate()}>
            Change number
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}
