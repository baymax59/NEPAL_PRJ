// The investigator's workspace: one case, with its header and tabs (docs/case-management/13, section 5).

import { ActionIcon, Alert, Badge, Box, Button, Center, Group, Loader, Paper, ScrollArea, Stack, Text, Title, Tooltip, UnstyledButton } from '@mantine/core'
import {
  IconBrain,
  IconFolder,
  IconHistory,
  IconHome,
  IconLink,
  IconMessages,
  IconPencil,
  IconLock,
  IconPhone,
  IconPlugConnected,
  IconReport,
  IconShieldCheck,
  IconUpload,
  IconUsers,
  IconPlus,
} from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { Suspense, useState, type ReactNode } from 'react'
import { Link, Outlet, useLocation, useNavigate, useParams } from 'react-router'
import { useAuth } from '../../auth/useAuth'
import { kh } from '../api'
import { roleLabel } from '../labels'
import type { CaseDetail } from '../types'
import { ClassificationBadge, Loaded, PersonName, PriorityBadge, WorkflowBadge } from '../ui'
import { CaseContext } from './context'
import { AddEvidenceDialog, CaseNameDialog, CaseNumberDialog, NoteDialog } from './dialogs'

export function CaseLayout() {
  const { caseId = '' } = useParams()
  const query = useQuery({ queryKey: ['kh', 'case', caseId], queryFn: () => kh.case(caseId) })
  return (
    <Loaded query={query}>
      {(detail) => (
        <CaseContext value={detail}>
          <CaseHeader detail={detail} />
          <CaseTabs detail={detail} />
          <Box mt="md">
            <Suspense fallback={<Center py="xl"><Loader size="sm" /></Center>}>
              <Outlet />
            </Suspense>
          </Box>
        </CaseContext>
      )}
    </Loaded>
  )
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <Box>
      <Text size="10px" c="dimmed" tt="uppercase" fw={600} style={{ letterSpacing: 0.5 }}>
        {label}
      </Text>
      <Box fz="sm">{children}</Box>
    </Box>
  )
}

function CaseHeader({ detail }: { detail: CaseDetail }) {
  const navigate = useNavigate()
  const [dialog, setDialog] = useState<null | 'note' | 'evidence' | 'number' | 'name'>(null)
  const archived = detail.workflow_status === 'archived'
  const fir = detail.official_references
  const toFiles = (folder: string) => navigate(`/kh/case/${detail.id}/files?folder=${encodeURIComponent(folder)}`)
  return (
    <Paper withBorder p="md" radius="sm">
      <Group justify="space-between" align="flex-start" gap="md">
        <Stack gap={6} style={{ minWidth: 0, flex: 1 }}>
          <Group gap="xs" wrap="wrap">
            <Text ff="monospace" fw={700} fz={19} c="hawk.3">
              {detail.display_id}
            </Text>
            {detail.can.rename_case && (
              <Tooltip label="Change the case number">
                <ActionIcon variant="subtle" color="gray" size="sm" aria-label="Change the case number" onClick={() => setDialog('number')}>
                  <IconPencil size={14} />
                </ActionIcon>
              </Tooltip>
            )}
            <WorkflowBadge value={detail.workflow_status} />
            {detail.my_role ? (
              <Badge variant="outline" color="gray" size="sm">
                You: {roleLabel(detail.my_role)}
              </Badge>
            ) : (
              <Badge variant="outline" color="gray" size="sm">
                You oversee this case
              </Badge>
            )}
          </Group>
          {detail.previous_numbers.length > 0 && (
            <Text size="xs" c="dimmed">
              Formerly {detail.previous_numbers.map((p) => p.old_number).filter((n, i, all) => all.indexOf(n) === i).join(', ')}
            </Text>
          )}
          <Group gap={6} align="center" wrap="nowrap">
            <Title order={2} size="h3" fw={600}>
              {detail.title}
            </Title>
            {detail.can.rename_case && (
              <Tooltip label="Edit case name (supervisor only)">
                <ActionIcon
                  variant="subtle"
                  color="gray"
                  size="sm"
                  aria-label="Edit case name"
                  onClick={() => setDialog('name')}
                >
                  <IconPencil size={14} />
                </ActionIcon>
              </Tooltip>
            )}
          </Group>
          <Group gap="xl" wrap="wrap" mt={2}>
            <Fact label="Type of case">{detail.case_type_label}</Fact>
            <Fact label="Official reference">{fir.length ? fir.join(', ') : <Text span c="dimmed" size="sm">none recorded</Text>}</Fact>
            <Fact label="Investigator">{detail.lead ? <PersonName person={detail.lead} /> : <Text span c="dimmed" size="sm">—</Text>}</Fact>
            <Fact label="Supervisor">{detail.supervisor ? <PersonName person={detail.supervisor} /> : <Text span c="dimmed" size="sm">—</Text>}</Fact>
            <Fact label="Priority">
              <PriorityBadge value={detail.priority} />
            </Fact>
            <Fact label="Classification">
              <ClassificationBadge value={detail.classification} />
            </Fact>
          </Group>
        </Stack>
        <Group gap={6} wrap="nowrap" className="no-print">
          {detail.can.add_files && (
            <>
              <Button size="xs" variant="default" leftSection={<IconPlus size={14} />} onClick={() => setDialog('note')}>
                New note
              </Button>
              <Button size="xs" leftSection={<IconUpload size={14} />} onClick={() => setDialog('evidence')}>
                Add exhibit
              </Button>
            </>
          )}
        </Group>
      </Group>
      {archived && (
        <Alert color="gray" mt="sm" p="xs" icon={<IconLock size={16} />}>
          <Text size="sm">Archived: this case can be read but nothing can be added to it. A Supervisor can reopen it.</Text>
        </Alert>
      )}
      {dialog === 'note' && <NoteDialog opened onClose={() => setDialog(null)} detail={detail} onAdded={toFiles} />}
      {dialog === 'evidence' && <AddEvidenceDialog opened onClose={() => setDialog(null)} detail={detail} onAdded={toFiles} />}
      {dialog === 'number' && <CaseNumberDialog opened onClose={() => setDialog(null)} detail={detail} />}
      {dialog === 'name' && <CaseNameDialog opened onClose={() => setDialog(null)} detail={detail} />}
    </Paper>
  )
}

const TABS: { path: string; label: string; icon: ReactNode; admin?: boolean; chat?: boolean }[] = [
  { path: '', label: 'Overview', icon: <IconHome size={15} /> },
  { path: 'files', label: 'Files', icon: <IconFolder size={15} /> },
  { path: 'team', label: 'Team', icon: <IconUsers size={15} /> },
  { path: 'chat', label: 'Chat', icon: <IconMessages size={15} />, chat: true },
  { path: 'history', label: 'History', icon: <IconHistory size={15} /> },
  { path: 'links', label: 'Links', icon: <IconLink size={15} /> },
  { path: 'reports', label: 'Reports', icon: <IconReport size={15} /> },
  { path: 'insights', label: 'Insights', icon: <IconBrain size={15} /> },
  { path: 'imports', label: 'Imports', icon: <IconPlugConnected size={15} /> },
  { path: 'cdr', label: 'CDR', icon: <IconPhone size={15} /> },
  { path: 'audit', label: 'Audit', icon: <IconShieldCheck size={15} />, admin: true },
]

function CaseTabs({ detail }: { detail: CaseDetail }) {
  const { pathname } = useLocation()
  const { user } = useAuth()
  const base = `/kh/case/${detail.id}`
  const current = pathname.slice(base.length + 1).split('/')[0]
  // only people on the team have the Chat tab; it shows how many messages are waiting
  const chat = useQuery({ queryKey: ['kh', 'case', detail.id, 'chat', 'threads'], queryFn: () => kh.chatThreads(detail.id), refetchInterval: 10_000, enabled: detail.can.chat })
  const unread = (chat.data ?? []).reduce((sum, t) => sum + t.unread, 0)
  return (
    <ScrollArea type="never" mt="sm" className="no-print">
      <Group gap={0} wrap="nowrap" style={{ borderBottom: '1px solid var(--mantine-color-default-border)' }}>
        {TABS.filter((t) => (!t.admin || user?.org_role === 'super_admin') && (!t.chat || detail.can.chat)).map((tab) => {
          const active = current === tab.path
          return (
            <UnstyledButton
              key={tab.path}
              component={Link}
              to={tab.path ? `${base}/${tab.path}` : base}
              px="sm"
              py={8}
              aria-current={active ? 'page' : undefined}
              style={{
                borderBottom: `2px solid ${active ? 'var(--mantine-color-hawk-4)' : 'transparent'}`,
                marginBottom: -1,
                whiteSpace: 'nowrap',
              }}
            >
              <Group gap={6} wrap="nowrap">
                <Box c={active ? undefined : 'dimmed'} style={{ display: 'flex' }}>
                  {tab.icon}
                </Box>
                <Text size="sm" fw={active ? 600 : 400} c={active ? undefined : 'dimmed'}>
                  {tab.label}
                </Text>
                {tab.chat && unread > 0 && (
                  <Badge size="xs" circle color="red" aria-label={`${unread} unread messages`}>
                    {unread}
                  </Badge>
                )}
              </Group>
            </UnstyledButton>
          )
        })}
      </Group>
    </ScrollArea>
  )
}
