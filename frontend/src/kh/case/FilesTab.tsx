// Files: the case's permanent folders, and the notes and exhibits in them (docs/case-management/13).

import { Alert, Anchor, Badge, Button, Divider, Drawer, Grid, Group, NavLink, Paper, Stack, Table, Text, Tooltip } from '@mantine/core'
import { IconArrowBackUp, IconFile, IconFileText, IconFingerprint, IconFolder, IconFolderPlus, IconLock, IconLockOpen, IconPencil, IconPlus, IconUpload } from '@tabler/icons-react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { formatBytes } from '../../lib/format'
import { kh } from '../api'
import { Comments } from '../Comments'
import { ContentView, DiffView } from '../content'
import { contentText } from '../diff'
import { toastDone, toastError } from '../feedback'
import { formatWhen } from '../time'
import { ARTIFACT_TYPES, humanize } from '../labels'
import type { ArtifactHistory, CaseDetail, EvidenceDetail, FileOut } from '../types'
import { ConfirmModal, EmptyState, Facts, Loaded, Panel, PersonName, When } from '../ui'
import { useCase } from './context'
import { ActiveContentWarning, AddEvidenceDialog, FolderDialog, NoteDialog } from './dialogs'
import { useRefreshCase } from './helpers'

export function FilesTab() {
  const detail = useCase()
  const [params, setParams] = useSearchParams()
  const folder = params.get('folder') ?? ''
  const open = params.get('open')
  const [dialog, setDialog] = useState<null | 'note' | 'evidence' | 'folder'>(null)
  const files = useQuery({
    queryKey: ['kh', 'case', detail.id, 'files', folder],
    queryFn: () => kh.files(detail.id, { folder: folder || undefined }),
  })
  const go = (next: Record<string, string | null>) =>
    setParams((current) => {
      const updated = new URLSearchParams(current)
      for (const [k, v] of Object.entries(next)) {
        if (v === null) updated.delete(k)
        else updated.set(k, v)
      }
      return updated
    })
  const total = detail.folders.reduce((sum, f) => sum + f.files, 0)

  return (
    <Stack gap="sm">
      <Group justify="space-between" wrap="wrap" gap="xs">
        <Text size="sm" c="dimmed">
          {folder ? `The files in the folder ${folder}.` : 'All the files of the case, folder by folder.'} Nothing is deleted: a wrong file is withdrawn, with a reason.
        </Text>
        {detail.can.add_files && (
          <Group gap="xs">
            {detail.can.add_folders && (
              <Button size="xs" variant="default" leftSection={<IconFolderPlus size={14} />} onClick={() => setDialog('folder')}>
                New folder
              </Button>
            )}
            <Button size="xs" variant="default" leftSection={<IconPlus size={14} />} onClick={() => setDialog('note')}>
              New note
            </Button>
            <Button size="xs" leftSection={<IconUpload size={14} />} onClick={() => setDialog('evidence')}>
              Add exhibit
            </Button>
          </Group>
        )}
      </Group>

      <Grid gap="sm">
        <Grid.Col span={{ base: 12, md: 3 }}>
        <Paper withBorder radius="sm" p={4}>
          <NavLink
            label="All folders"
            leftSection={<IconFolder size={16} />}
            rightSection={<Badge size="xs" color="gray">{total}</Badge>}
            active={!folder}
            onClick={() => go({ folder: null })}
          />
          {detail.folders.map((f) => (
            <NavLink
              key={f.id}
              label={f.name}
              leftSection={<IconFolder size={16} color="var(--mantine-color-hawk-4)" />}
              rightSection={<Badge size="xs" color="gray">{f.files}</Badge>}
              active={folder === f.name}
              onClick={() => go({ folder: f.name })}
            />
          ))}
        </Paper>
        </Grid.Col>

        <Grid.Col span={{ base: 12, md: 9 }}>
        <Stack gap="xs">
          <Loaded query={files}>
            {(view) => (
              <Paper withBorder radius="sm">
                {view.files.some((f) => f.status === 'withdrawn') && (
                  <Alert color="red" variant="light" radius={0} icon={<IconArrowBackUp size={16} />} title="Withdrawn by the team">
                    The files in red were withdrawn by the Investigator who leads the case. They are no longer shown to the team, and stay here for you, with who withdrew them and why.
                    Nothing can be deleted.
                  </Alert>
                )}
                {view.files.length === 0 ? (
                  <EmptyState title={folder ? 'This folder is empty' : 'No files yet'}>{detail.can.add_files ? 'Add an exhibit or a note here.' : null}</EmptyState>
                ) : (
                  <Table>
                    <Table.Thead>
                      <Table.Tr>
                        <Table.Th>Name</Table.Th>
                        <Table.Th>Number</Table.Th>
                        <Table.Th>Kind</Table.Th>
                        <Table.Th>Version</Table.Th>
                        <Table.Th>Added</Table.Th>
                      </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                      {view.files.map((file) => (
                        <FileRow key={file.id} file={file} showFolder={!folder} onOpen={() => go({ open: file.id })} />
                      ))}
                    </Table.Tbody>
                  </Table>
                )}
              </Paper>
            )}
          </Loaded>
        </Stack>
        </Grid.Col>
      </Grid>

      {open && files.data && <FileDrawer detail={detail} file={files.data.files.find((f) => f.id === open)} fileId={open} onClose={() => go({ open: null })} />}
      {dialog === 'note' && <NoteDialog opened onClose={() => setDialog(null)} detail={detail} folder={folder || undefined} onAdded={(f) => go({ folder: f })} />}
      {dialog === 'evidence' && <AddEvidenceDialog opened onClose={() => setDialog(null)} detail={detail} folder={folder || undefined} onAdded={(f) => go({ folder: f })} />}
      {dialog === 'folder' && <FolderDialog opened onClose={() => setDialog(null)} detail={detail} onAdded={(f) => go({ folder: f })} />}
    </Stack>
  )
}

function FileRow({ file, showFolder, onOpen }: { file: FileOut; showFolder: boolean; onOpen: () => void }) {
  const withdrawn = file.status === 'withdrawn'
  const evidence = file.kind === 'evidence'
  return (
    <Table.Tr
      data-withdrawn={withdrawn ? 'true' : undefined}
      style={withdrawn ? { background: 'var(--mantine-color-red-light)', boxShadow: 'inset 4px 0 0 var(--mantine-color-red-6)' } : undefined}
    >
      <Table.Td>
        <Group gap={8} wrap="nowrap">
          {evidence ? <IconFingerprint size={16} color="var(--mantine-color-teal-5)" /> : file.type === 'link' ? <IconFile size={16} /> : <IconFileText size={16} />}
          <Anchor size="sm" onClick={onOpen} fw={withdrawn ? 600 : undefined}>
            {file.title}
          </Anchor>
          {file.sealed && (
            <Tooltip label="Sealed: only the supervisor and administrators can open it">
              <IconLock size={14} color="var(--mantine-color-orange-5)" />
            </Tooltip>
          )}
          {withdrawn && (
            <Badge size="xs" color="red">
              withdrawn
            </Badge>
          )}
        </Group>
        {withdrawn && (
          <Text size="xs" mt={2} style={{ color: 'var(--mantine-color-red-light-color)' }}>
            Withdrawn{file.withdrawn_by ? ` by ${file.withdrawn_by.display_name}` : ''}
            {file.withdrawn_at ? ` on ${formatWhen(file.withdrawn_at)}` : ''}
            {file.withdrawn_reason ? `: ${file.withdrawn_reason}` : ''}
          </Text>
        )}
        {showFolder && (
          <Text size="xs" c="dimmed">
            {file.folder}
          </Text>
        )}
      </Table.Td>
      <Table.Td>
        <Text size="xs" ff="monospace">
          {file.display_id}
        </Text>
      </Table.Td>
      <Table.Td>
        <Badge size="xs" color={evidence ? 'teal' : 'gray'} variant="light">
          {evidence ? humanize(file.type) : (ARTIFACT_TYPES[file.type] ?? humanize(file.type))}
        </Badge>
        {file.evidence && (
          <Text size="xs" c="dimmed">
            {file.evidence.mime_type} · {formatBytes(file.evidence.size_bytes)}
          </Text>
        )}
      </Table.Td>
      <Table.Td>
        <Text size="xs" c="dimmed">
          {evidence ? 'original' : file.version_number ? `version ${file.version_number}` : ''}
        </Text>
      </Table.Td>
      <Table.Td>
        <Group gap={6} wrap="nowrap">
          <PersonName person={file.created_by} size="xs" />
          <When at={file.updated_at} size="xs" />
        </Group>
      </Table.Td>
    </Table.Tr>
  )
}

/** One file: its content, its versions (with the differences), and what can be done with it. */
export function FileDrawer({ detail, file, fileId, onClose }: { detail: CaseDetail; file?: FileOut; fileId: string; onClose: () => void }) {
  const evidence = file?.kind === 'evidence'
  return (
    <Drawer opened onClose={onClose} position="right" size="xl" title={<Text fw={600}>{file?.title ?? 'File'}</Text>}>
      {file ? evidence ? <ExhibitView detail={detail} id={fileId} onClose={onClose} /> : <NoteView detail={detail} id={fileId} onClose={onClose} /> : (
        <Alert color="gray">This file isn't in the list: it may have been withdrawn, or you may not have access to it.</Alert>
      )}
    </Drawer>
  )
}

function ExhibitView({ detail, id, onClose }: { detail: CaseDetail; id: string; onClose: () => void }) {
  const refresh = useRefreshCase(detail.id)
  const [withdrawing, setWithdrawing] = useState(false)
  const query = useQuery({ queryKey: ['kh', 'case', detail.id, 'evidence', id], queryFn: () => kh.evidence(id) })
  const withdraw = useMutation({
    mutationFn: (reason: string) => kh.withdrawEvidence(id, reason),
    onSuccess: () => {
      toastDone('Withdrawn. It stays in the history.')
      refresh()
      setWithdrawing(false)
      onClose()
    },
    onError: (error) => toastError(error),
  })
  return (
    <Loaded query={query}>
      {(e: EvidenceDetail) => (
        <Stack gap="md">
          <Facts
            items={[
              ['Number', <Text key="i" size="sm" ff="monospace">{e.display_id}</Text>],
              ['Folder', e.folder],
              ['Kind', `Exhibit: ${humanize(e.evidence_type)}`],
              ['Status', e.status === 'withdrawn' ? `Withdrawn: ${e.withdrawn_reason ?? ''}` : 'Active'],
              ['File', `${e.original_filename} · ${e.mime_type} · ${formatBytes(e.size_bytes)}`],
              ['Added', <span key="a"><PersonName person={e.uploaded_by} size="xs" /> <When at={e.uploaded_at} size="xs" /></span>],
            ]}
          />
          <Paper withBorder p="sm">
            <Stack gap="xs">
              {e.sealed && (
                <Alert color="orange" p="xs" icon={<IconLock size={16} />}>
                  Sealed exhibit.
                </Alert>
              )}
              {e.category === 'executable' && <ActiveContentWarning />}
              <Button component={Link} to={`/kh/evidence/${e.id}`} leftSection={<IconFingerprint size={16} />} variant="light">
                Open the exhibit: integrity, custody, preview
              </Button>
            </Stack>
          </Paper>
          {e.can.withdraw && (
            <Group gap="xs">
              <Button size="xs" variant="default" color="orange" leftSection={<IconArrowBackUp size={14} />} onClick={() => setWithdrawing(true)}>
                Withdraw
              </Button>
            </Group>
          )}
          <Divider label="Comments" labelPosition="left" />
          <Comments caseId={detail.id} targetType="evidence" targetId={e.id} canWrite={detail.can.comment} />
          <ConfirmModal
            opened={withdrawing}
            onClose={() => setWithdrawing(false)}
            title={`Withdraw ${e.title}?`}
            confirmLabel="Withdraw"
            color="orange"
            reason="required"
            reasonLabel="Why is it withdrawn?"
            loading={withdraw.isPending}
            onConfirm={(reason) => withdraw.mutate(reason)}
          >
            <Text size="sm">It leaves the current view of the case. Nothing is deleted: the exhibit and its custody record stay in the history.</Text>
          </ConfirmModal>
        </Stack>
      )}
    </Loaded>
  )
}

function NoteView({ detail, id, onClose }: { detail: CaseDetail; id: string; onClose: () => void }) {
  const refresh = useRefreshCase(detail.id)
  const [action, setAction] = useState<null | 'revise' | 'withdraw' | 'seal' | 'unseal'>(null)
  const query = useQuery({ queryKey: ['kh', 'case', detail.id, 'note', id], queryFn: () => kh.artifactVersions(id) })
  const withdraw = useMutation({
    mutationFn: (reason: string) => kh.withdrawNote(id, reason),
    onSuccess: () => {
      toastDone('Withdrawn. It stays in the history.')
      refresh()
      setAction(null)
      onClose()
    },
    onError: (error) => toastError(error),
  })
  const seal = useMutation({
    mutationFn: ({ sealIt, reason }: { sealIt: boolean; reason: string }) => (sealIt ? kh.sealArtifact(id, reason) : kh.unsealArtifact(id, reason)),
    onSuccess: () => {
      toastDone('Done')
      refresh()
      setAction(null)
    },
    onError: (error) => toastError(error),
  })
  return (
    <Loaded query={query}>
      {(note: ArtifactHistory) => {
        const latest = note.versions[note.versions.length - 1]
        return (
          <Stack gap="md">
            <Facts
              items={[
                ['Number', <Text key="i" size="sm" ff="monospace">{note.display_id}</Text>],
                ['Folder', note.folder],
                ['Kind', ARTIFACT_TYPES[note.artifact_type] ?? humanize(note.artifact_type)],
                ['Status', note.status === 'withdrawn' ? `Withdrawn: ${note.withdrawn_reason ?? ''}` : 'Active'],
                ['Version', latest ? `version ${latest.version_number} of ${note.versions.length}` : null],
              ]}
            />
            {note.sealed && (
              <Alert color="orange" p="xs" icon={<IconLock size={16} />}>
                Sealed: only the supervisor and administrators can open it. {note.sealed_reason}
              </Alert>
            )}
            <Panel title="Content">
              <ContentView content={(latest?.content ?? null) as Record<string, unknown> | null} />
            </Panel>

            <Group gap="xs">
              {note.can.revise && (
                <Button size="xs" variant="default" leftSection={<IconPencil size={14} />} onClick={() => setAction('revise')}>
                  New version
                </Button>
              )}
              {note.can.withdraw && (
                <Button size="xs" variant="default" color="orange" leftSection={<IconArrowBackUp size={14} />} onClick={() => setAction('withdraw')}>
                  Withdraw
                </Button>
              )}
              {note.can.seal && (
                <Button size="xs" variant="default" leftSection={note.sealed ? <IconLockOpen size={14} /> : <IconLock size={14} />} onClick={() => setAction(note.sealed ? 'unseal' : 'seal')}>
                  {note.sealed ? 'Unseal' : 'Seal'}
                </Button>
              )}
            </Group>

            <Panel title="Versions">
              <Stack gap="sm">
                {[...note.versions].reverse().map((version, index, list) => {
                  const previous = list[index + 1]
                  return (
                    <Paper key={version.id} withBorder p="xs">
                      <Group justify="space-between" mb={4}>
                        <Group gap="xs">
                          <Badge size="sm" color="gray">
                            version {version.version_number}
                          </Badge>
                          <PersonName person={version.author} size="xs" />
                          <When at={version.created_at} size="xs" />
                        </Group>
                      </Group>
                      {version.change_note && (
                        <Text size="xs" c="dimmed" mb={4}>
                          “{version.change_note}”
                        </Text>
                      )}
                      {previous ? (
                        <DiffView before={previous.content} after={version.content} maxHeight={260} />
                      ) : (
                        <Text size="xs" c="dimmed">
                          First version.
                        </Text>
                      )}
                    </Paper>
                  )
                })}
              </Stack>
            </Panel>

            <Divider label="Comments" labelPosition="left" />
            <Comments caseId={detail.id} targetType="artifact" targetId={note.id} canWrite={detail.can.comment} />

            {action === 'revise' && latest && (
              <NoteDialog
                opened
                onClose={() => setAction(null)}
                detail={detail}
                revise={{ artifactId: note.id, title: note.title, text: contentText(latest.content as Record<string, unknown> | null), version: latest.version_number }}
              />
            )}
            <ConfirmModal
              opened={action === 'withdraw'}
              onClose={() => setAction(null)}
              title={`Withdraw ${note.title}?`}
              confirmLabel="Withdraw"
              color="orange"
              reason="required"
              reasonLabel="Why is it withdrawn?"
              loading={withdraw.isPending}
              onConfirm={(reason) => withdraw.mutate(reason)}
            >
              <Text size="sm">It leaves the current view of the case. Nothing is deleted: every version stays in the history.</Text>
            </ConfirmModal>
            <ConfirmModal
              opened={action === 'seal' || action === 'unseal'}
              onClose={() => setAction(null)}
              title={action === 'seal' ? 'Seal this note?' : 'Unseal this note?'}
              confirmLabel={action === 'seal' ? 'Seal' : 'Unseal'}
              reason="required"
              loading={seal.isPending}
              onConfirm={(reason) => seal.mutate({ sealIt: action === 'seal', reason })}
            >
              <Text size="sm">
                {action === 'seal' ? 'Only the supervisor and administrators will be able to open it.' : 'Everyone on the case will be able to open it again.'}
              </Text>
            </ConfirmModal>
          </Stack>
        )
      }}
    </Loaded>
  )
}
