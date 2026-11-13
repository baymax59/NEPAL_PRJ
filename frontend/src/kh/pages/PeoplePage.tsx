// People and stations (phase R-4): the people at your stations, the register of officers (an account is made only for an officer in it)
// and the police stations. What is offered depends on the role; the backend checks every request again and answers "not found" for
// people and stations you cannot reach. Nothing here deletes anything: an account is ended (and can be restored), a station is marked inactive.

import {
  Alert,
  Badge,
  Button,
  Code,
  FileInput,
  Group,
  Menu,
  Modal,
  MultiSelect,
  Select,
  Stack,
  Switch,
  Table,
  Tabs,
  Text,
  Textarea,
  TextInput,
  Tooltip,
} from '@mantine/core'
import { useDebouncedValue } from '@mantine/hooks'
import { IconBuildingCommunity, IconDots, IconFileImport, IconIdBadge2, IconInfoCircle, IconKey, IconPlus, IconUserPlus, IconUsers } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { UserAvatar } from '../../components/UserAvatar'
import { useAuth } from '../../auth/useAuth'
import { kh } from '../api'
import { toastDone, toastError } from '../feedback'
import { CLASSIFICATIONS, humanize, roleLabel } from '../labels'
import type { AccountRow, OfficerImportResult, OfficerOut, PasswordIssued, PeopleCapabilities, StationSummary } from '../types'
import { ConfirmModal, Copy, EmptyState, Loaded, PageHeader, Panel, When } from '../ui'

const ALL_ROLES = ['administrator', 'supervisor', 'investigator', 'sub_investigator', 'analyst', 'viewer']
const CSV_TEMPLATE = 'officer_number,full_name,rank,station_code,highest_role\nEX-0001,Example Officer (fictional),Inspector,HQ,investigator\n'

export function PeoplePage() {
  const caps = useQuery({ queryKey: ['kh', 'people', 'capabilities'], queryFn: () => kh.peopleCapabilities(), staleTime: 60_000 })
  return (
    <Stack gap="md">
      <PageHeader eyebrow="Administration" title="People and stations">
        <Text size="sm" c="dimmed">
          Who works where. An account is made only for an officer in the register: by the person directly above (its owner chooses their own password at the first login), or by the officer on the log in page. A login the
          officer made themselves is view-only until you raise its role and clearance.
        </Text>
      </PageHeader>
      <Loaded query={caps}>
        {(c) =>
          c.sees_people ? (
            <Tabs defaultValue="people" keepMounted={false}>
              <Tabs.List mb="md">
                <Tabs.Tab value="people" leftSection={<IconUsers size={15} />}>
                  People
                </Tabs.Tab>
                <Tabs.Tab value="officers" leftSection={<IconIdBadge2 size={15} />}>
                  Register of officers
                </Tabs.Tab>
                <Tabs.Tab value="stations" leftSection={<IconBuildingCommunity size={15} />}>
                  Police stations
                </Tabs.Tab>
              </Tabs.List>
              <Tabs.Panel value="people">
                <PeopleTab caps={c} />
              </Tabs.Panel>
              <Tabs.Panel value="officers">
                <OfficersTab caps={c} />
              </Tabs.Panel>
              <Tabs.Panel value="stations">
                <StationsTab caps={c} />
              </Tabs.Panel>
            </Tabs>
          ) : (
            <Alert color="gray" icon={<IconInfoCircle size={18} />} title="Not available for your role">
              Only Super Admins, Administrators, Supervisors and Investigators work with people and stations.
            </Alert>
          )
        }
      </Loaded>
    </Stack>
  )
}

function useRefreshPeople() {
  const client = useQueryClient()
  return () => {
    void client.invalidateQueries({ queryKey: ['kh', 'people'] })
    void client.invalidateQueries({ queryKey: ['kh', 'stations'] })
  }
}

// ------------------------------------------------------------------ people

function PeopleTab({ caps }: { caps: PeopleCapabilities }) {
  const [search, setSearch] = useState('')
  const [q] = useDebouncedValue(search.trim(), 300)
  const people = useQuery({ queryKey: ['kh', 'people', 'accounts', q], queryFn: () => kh.accounts(q || undefined) })
  const [creating, setCreating] = useState(false)
  const [issued, setIssued] = useState<{ password: string; who: string } | null>(null)
  const [role, setRole] = useState<AccountRow | null>(null)
  const [level, setLevel] = useState<AccountRow | null>(null)
  const [places, setPlaces] = useState<AccountRow | null>(null)
  const [confirm, setConfirm] = useState<{ kind: 'reset' | 'end' | 'restore'; person: AccountRow } | null>(null)
  const refresh = useRefreshPeople()
  const action = useMutation({
    mutationFn: ({ kind, person, reason }: { kind: 'reset' | 'end' | 'restore'; person: AccountRow; reason: string }): Promise<AccountRow | PasswordIssued> =>
      kind === 'reset' ? kh.resetPassword(person.id, reason) : kh.setAccountActive(person.id, kind === 'restore', reason),
    onSuccess: (result, { kind, person }) => {
      refresh()
      setConfirm(null)
      if (kind === 'reset' && 'temporary_password' in result) setIssued({ password: result.temporary_password, who: person.display_name })
      else toastDone(kind === 'end' ? `${person.display_name}'s account was ended. Their work stays, attributed to them.` : `${person.display_name}'s account is active again`)
    },
    onError: (error) => toastError(error, 'Not done'),
  })
  return (
    <Stack gap="sm">
      <Group justify="space-between" wrap="wrap">
        <TextInput placeholder="Search by name or username" value={search} onChange={(e) => setSearch(e.currentTarget.value)} w={300} />
        {caps.can_create_accounts && (
          <Button leftSection={<IconUserPlus size={16} />} onClick={() => setCreating(true)}>
            Create an account
          </Button>
        )}
      </Group>
      <Panel p="0">
        <Loaded query={people}>
          {(rows) =>
            rows.length === 0 ? (
              <EmptyState title="Nobody found">People at your stations appear here.</EmptyState>
            ) : (
              <Table verticalSpacing="xs" highlightOnHover>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Person</Table.Th>
                    <Table.Th>Role</Table.Th>
                    <Table.Th>Station</Table.Th>
                    <Table.Th>Officer ID</Table.Th>
                    <Table.Th>Status</Table.Th>
                    <Table.Th />
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {rows.map((p) => (
                    <Table.Tr key={p.id}>
                      <Table.Td>
                        <Group gap="sm" wrap="nowrap" align="flex-start">
                          <UserAvatar id={p.id} name={p.display_name} version={p.photo} size={34} />
                          <div>
                            <Text size="sm" fw={600}>
                              {p.display_name}
                            </Text>
                            <Text size="xs" c="dimmed">
                              @{p.username}
                            </Text>
                            {(p.job_title || p.email || p.phone) && (
                              <Text size="xs" c="dimmed">
                                {[p.job_title, p.email, p.phone].filter(Boolean).join(' · ')}
                              </Text>
                            )}
                          </div>
                        </Group>
                      </Table.Td>
                      <Table.Td>
                        <Badge variant="light" color="hawk">
                          {roleLabel(p.org_role)}
                        </Badge>
                        {p.org_role_since && (
                          <Text size="xs" c="dimmed">
                            since <When at={p.org_role_since} size="xs" />
                          </Text>
                        )}
                      </Table.Td>
                      <Table.Td>
                        <Group gap={4}>
                          {p.org_role === 'super_admin' ? (
                            <Badge variant="outline" color="gray" size="sm">
                              all stations
                            </Badge>
                          ) : (
                            p.stations.map((s) => (
                              <Tooltip key={s.id} label={s.name}>
                                <Badge variant="outline" color="gray" size="sm">
                                  {s.code}
                                </Badge>
                              </Tooltip>
                            ))
                          )}
                        </Group>
                      </Table.Td>
                      <Table.Td>
                        <Text size="xs" ff="monospace">
                          {p.officer?.officer_number ?? '—'}
                        </Text>
                      </Table.Td>
                      <Table.Td>
                        <Group gap={4}>
                          {!p.is_active && <Badge color="red" size="sm">ended</Badge>}
                          {p.must_change_password && p.is_active && (
                            <Tooltip label="Has not yet chosen their own password">
                              <Badge color="yellow" size="sm">temporary password</Badge>
                            </Tooltip>
                          )}
                          {p.is_active && !p.must_change_password && <Badge color="green" variant="light" size="sm">active</Badge>}
                        </Group>
                      </Table.Td>
                      <Table.Td>
                        <PersonMenu person={p} onRole={() => setRole(p)} onClearance={() => setLevel(p)} onStations={() => setPlaces(p)} onConfirm={(kind) => setConfirm({ kind, person: p })} />
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            )
          }
        </Loaded>
      </Panel>
      <CreateAccountModal opened={creating} onClose={() => setCreating(false)} onCreated={(password, who) => setIssued({ password, who })} />
      <TemporaryPasswordModal issued={issued} onClose={() => setIssued(null)} />
      {role && <ChangeRoleModal person={role} onClose={() => setRole(null)} />}
      {level && <ChangeClearanceModal person={level} onClose={() => setLevel(null)} />}
      {places && <StationsModal person={places} onClose={() => setPlaces(null)} />}
      <ConfirmModal
        opened={confirm !== null}
        onClose={() => setConfirm(null)}
        title={confirm?.kind === 'reset' ? 'Reset password' : confirm?.kind === 'end' ? 'End this account' : 'Restore this account'}
        confirmLabel={confirm?.kind === 'reset' ? 'Issue a temporary password' : confirm?.kind === 'end' ? 'End the account' : 'Restore the account'}
        color={confirm?.kind === 'end' ? 'red' : 'hawk'}
        reason="required"
        loading={action.isPending}
        onConfirm={(reason) => confirm && action.mutate({ kind: confirm.kind, person: confirm.person, reason })}
      >
        {confirm?.kind === 'reset' && (
          <Text size="sm">A new temporary password is made for {confirm.person.display_name}. It is shown once, to you; {confirm.person.display_name} must choose their own at the next login. The old password stops working.</Text>
        )}
        {confirm?.kind === 'end' && (
          <Text size="sm">{confirm.person.display_name} can no longer log in. Nothing they did is touched: their work, notes and exhibits stay, credited to them. You can restore the account later.</Text>
        )}
        {confirm?.kind === 'restore' && <Text size="sm">{confirm.person.display_name} can log in again with their own password.</Text>}
      </ConfirmModal>
    </Stack>
  )
}

function PersonMenu({ person, onRole, onClearance, onStations, onConfirm }: { person: AccountRow; onRole: () => void; onClearance: () => void; onStations: () => void; onConfirm: (kind: 'reset' | 'end' | 'restore') => void }) {
  const c = person.can
  if (!c.change_role && !c.change_clearance && !c.set_stations && !c.reset_password && !c.deactivate && !c.reactivate) return null
  return (
    <Menu position="bottom-end">
      <Menu.Target>
        <Button size="compact-xs" variant="subtle" color="gray" aria-label={`Actions for ${person.display_name}`}>
          <IconDots size={16} />
        </Button>
      </Menu.Target>
      <Menu.Dropdown>
        {c.change_role && <Menu.Item onClick={onRole}>Change role…</Menu.Item>}
        {c.change_clearance && <Menu.Item onClick={onClearance}>Change clearance…</Menu.Item>}
        {c.set_stations && <Menu.Item onClick={onStations}>Stations…</Menu.Item>}
        {c.reset_password && <Menu.Item leftSection={<IconKey size={14} />} onClick={() => onConfirm('reset')}>Reset password…</Menu.Item>}
        {c.deactivate && <Menu.Item color="red" onClick={() => onConfirm('end')}>End account…</Menu.Item>}
        {c.reactivate && <Menu.Item onClick={() => onConfirm('restore')}>Restore account…</Menu.Item>}
      </Menu.Dropdown>
    </Menu>
  )
}

/** The temporary password, once. */
function TemporaryPasswordModal({ issued, onClose }: { issued: { password: string; who: string } | null; onClose: () => void }) {
  return (
    <Modal opened={issued !== null} onClose={onClose} title={<Text fw={600}>Temporary password for {issued?.who}</Text>} closeOnClickOutside={false} size="md">
      <Stack gap="sm">
        <Group justify="center" gap="xs">
          <Code fz="xl" fw={700} p="sm" data-testid="temporary-password">
            {issued?.password}
          </Code>
          <Copy value={issued?.password ?? ''} />
        </Group>
        <Alert color="yellow" variant="light" icon={<IconInfoCircle size={18} />}>
          This is shown only now. Give it to {issued?.who} in private. They must choose their own password at the first login. If it is lost, reset it.
        </Alert>
        <Group justify="flex-end">
          <Button onClick={onClose}>I have handed it over</Button>
        </Group>
      </Stack>
    </Modal>
  )
}

function suggestUsername(fullName: string): string {
  const words = fullName
    .replace(/\(.*?\)/g, ' ')
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter(Boolean)
  return words.slice(0, 2).join('.')
}

function CreateAccountModal({ opened, onClose, onCreated, officer: preset }: { opened: boolean; onClose: () => void; onCreated: (password: string, who: string) => void; officer?: OfficerOut | null }) {
  const { user } = useAuth()
  const refresh = useRefreshPeople()
  const [search, setSearch] = useState('')
  const [debounced] = useDebouncedValue(search, 250)
  const officers = useQuery({ queryKey: ['kh', 'people', 'officers', 'free', debounced], queryFn: () => kh.officers({ q: debounced || undefined, free: true }), enabled: opened && !preset })
  const stations = useQuery({ queryKey: ['kh', 'people', 'stations'], queryFn: () => kh.peopleStations(), enabled: opened })
  const [chosen, setChosen] = useState<OfficerOut | null>(null)
  const officer = preset ?? chosen
  const [role, setRole] = useState<string | null>(null)
  const [username, setUsername] = useState('')
  const [name, setName] = useState('')
  const [clearance, setClearance] = useState<string | null>(null)
  const [extra, setExtra] = useState<string[]>([])
  const allowedClearances = CLASSIFICATIONS.slice(0, CLASSIFICATIONS.indexOf(user?.clearance ?? 'internal') + 1)
  const effectiveRole = role ?? officer?.creatable_roles[officer.creatable_roles.length - 1] ?? null
  const effectiveClearance = clearance ?? (allowedClearances.includes('restricted') ? 'restricted' : (allowedClearances[allowedClearances.length - 1] ?? 'internal'))
  const effectiveUsername = username || (officer ? suggestUsername(officer.full_name) : '')
  const effectiveName = name || officer?.full_name || ''
  const mutation = useMutation({
    mutationFn: () =>
      kh.createAccount({
        officer_number: officer!.officer_number,
        username: effectiveUsername.trim(),
        display_name: effectiveName.trim(),
        role: effectiveRole!,
        clearance: effectiveClearance,
        extra_station_ids: effectiveRole === 'administrator' ? extra : [],
      }),
    onSuccess: (result) => {
      refresh()
      toastDone(`Account @${result.person.username} created`)
      onCreated(result.temporary_password, result.person.display_name)
      reset()
      onClose()
    },
    onError: (error) => toastError(error, 'The account was not created'),
  })
  const reset = () => {
    setChosen(null)
    setRole(null)
    setUsername('')
    setName('')
    setClearance(null)
    setExtra([])
    setSearch('')
  }
  const options = (officers.data ?? []).map((o) => ({ value: o.officer_number, label: `${o.officer_number} · ${o.full_name} (${o.rank}, ${o.station.code})`, disabled: o.creatable_roles.length === 0 }))
  return (
    <Modal opened={opened} onClose={() => { reset(); onClose() }} title={<Text fw={600}>Create an account</Text>} size="lg">
      <Stack gap="sm">
        {preset ? (
          <Alert color="gray" variant="light">
            For {preset.officer_number} · {preset.full_name} ({preset.rank}, station {preset.station.code}).
          </Alert>
        ) : (
          <Select
            label="Officer in the register"
            description="An account is made only for an officer in the register, once. Officers you cannot make an account for are greyed out."
            placeholder="Type an officer ID or name"
            searchable
            data={options}
            searchValue={search}
            onSearchChange={setSearch}
            filter={({ options: all }) => all}
            nothingFoundMessage={officers.isFetching ? 'Searching…' : 'No officer without an account found. Is the officer in the register?'}
            value={chosen?.officer_number ?? null}
            onChange={(number) => {
              setChosen(officers.data?.find((o) => o.officer_number === number) ?? null)
              setRole(null)
              setUsername('')
              setName('')
            }}
            required
          />
        )}
        {officer && (
          <>
            <Select
              label="Role"
              description={`The register allows ${officer.full_name} at most: ${roleLabel(officer.highest_role)}.`}
              data={officer.creatable_roles.map((r) => ({ value: r, label: roleLabel(r) }))}
              value={effectiveRole}
              onChange={setRole}
              allowDeselect={false}
              required
            />
            <Group grow align="flex-start">
              <TextInput label="Username" description="Lower-case letters, digits, '.', '_' or '-'" value={effectiveUsername} onChange={(e) => setUsername(e.currentTarget.value.toLowerCase())} required />
              <TextInput label="Name shown" value={effectiveName} onChange={(e) => setName(e.currentTarget.value)} required />
            </Group>
            <Select
              label="Clearance"
              description="The most sensitive cases this person may open. You cannot give more than your own."
              data={allowedClearances.map((c) => ({ value: c, label: c }))}
              value={effectiveClearance}
              onChange={setClearance}
              allowDeselect={false}
            />
            {effectiveRole === 'administrator' && (
              <MultiSelect
                label="More stations (besides the officer's own)"
                data={(stations.data ?? []).filter((s) => s.id !== officer.station.id && s.status === 'active').map((s) => ({ value: s.id, label: `${s.code}: ${s.name}` }))}
                value={extra}
                onChange={setExtra}
                placeholder={extra.length ? undefined : 'Optional'}
                searchable
                clearable
              />
            )}
            <Alert color="gray" variant="light" icon={<IconInfoCircle size={18} />}>
              The account works at station {officer.station.code} (taken from the register). A temporary password is made and shown once; its owner chooses their own at the first login.
            </Alert>
          </>
        )}
        <Group justify="flex-end">
          <Button variant="default" onClick={() => { reset(); onClose() }}>
            Cancel
          </Button>
          <Button disabled={!officer || !effectiveRole || effectiveUsername.trim().length < 3 || effectiveName.trim().length < 3} loading={mutation.isPending} onClick={() => mutation.mutate()}>
            Create account
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}

function ChangeRoleModal({ person, onClose }: { person: AccountRow; onClose: () => void }) {
  const refresh = useRefreshPeople()
  const [role, setRole] = useState<string | null>(null)
  const [reason, setReason] = useState('')
  const mutation = useMutation({
    mutationFn: () => kh.changeRole(person.id, role!, reason.trim()),
    onSuccess: (updated) => {
      refresh()
      toastDone(`${updated.display_name} is now ${roleLabel(updated.org_role)}`)
      onClose()
    },
    onError: (error) => toastError(error, 'The role was not changed'),
  })
  return (
    <Modal opened onClose={onClose} title={<Text fw={600}>Change the role of {person.display_name}</Text>} size="md">
      <Stack gap="sm">
        <Text size="sm">
          Now: <b>{roleLabel(person.org_role)}</b>
        </Text>
        <Select label="New role" data={person.can.allowed_roles.map((r) => ({ value: r, label: roleLabel(r) }))} value={role} onChange={setRole} required />
        <Textarea label="Reason (kept in the history)" value={reason} onChange={(e) => setReason(e.currentTarget.value)} autosize minRows={2} maxLength={500} required />
        <Alert color="gray" variant="light" icon={<IconInfoCircle size={18} />}>
          A change of role adds no power over cases that already exist: the new role's powers reach only cases registered from now on. What {person.display_name} did before stays as it was.
        </Alert>
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={!role || reason.trim().length < 5} loading={mutation.isPending} onClick={() => mutation.mutate()}>
            Change role
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}

function ChangeClearanceModal({ person, onClose }: { person: AccountRow; onClose: () => void }) {
  const refresh = useRefreshPeople()
  const [level, setLevel] = useState<string | null>(null)
  const [reason, setReason] = useState('')
  const mutation = useMutation({
    mutationFn: () => kh.changeClearance(person.id, level!, reason.trim()),
    onSuccess: (updated) => {
      refresh()
      toastDone(`${updated.display_name} now has ${humanize(updated.clearance)} clearance`)
      onClose()
    },
    onError: (error) => toastError(error, 'The clearance was not changed'),
  })
  return (
    <Modal opened onClose={onClose} title={<Text fw={600}>Change the clearance of {person.display_name}</Text>} size="md">
      <Stack gap="sm">
        <Text size="sm">
          Now: <b>{humanize(person.clearance)}</b>
        </Text>
        <Select label="New clearance" data={person.can.allowed_clearances.map((c) => ({ value: c, label: humanize(c) }))} value={level} onChange={setLevel} required />
        <Textarea label="Reason (kept in the history)" value={reason} onChange={(e) => setReason(e.currentTarget.value)} autosize minRows={2} maxLength={500} required />
        <Alert color="gray" variant="light" icon={<IconInfoCircle size={18} />}>
          The clearance is the most sensitive level {person.display_name} may see. You can give no more than your own. Cases still show only to people on their team (or who oversee them).
        </Alert>
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={!level || reason.trim().length < 5} loading={mutation.isPending} onClick={() => mutation.mutate()}>
            Change clearance
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}

function StationsModal({ person, onClose }: { person: AccountRow; onClose: () => void }) {
  const refresh = useRefreshPeople()
  const stations = useQuery({ queryKey: ['kh', 'people', 'stations'], queryFn: () => kh.peopleStations() })
  const several = person.org_role === 'administrator'
  const [chosen, setChosen] = useState<string[]>(person.stations.map((s) => s.id))
  const [reason, setReason] = useState('')
  const mutation = useMutation({
    mutationFn: () => kh.setStations(person.id, chosen, reason.trim()),
    onSuccess: (updated) => {
      refresh()
      toastDone(`${updated.display_name} now works at ${updated.stations.map((s) => s.code).join(', ')}`)
      onClose()
    },
    onError: (error) => toastError(error, 'The stations were not changed'),
  })
  const data = (stations.data ?? []).filter((s) => s.status === 'active' || chosen.includes(s.id)).map((s) => ({ value: s.id, label: `${s.code}: ${s.name}` }))
  return (
    <Modal opened onClose={onClose} title={<Text fw={600}>Stations of {person.display_name}</Text>} size="md">
      <Stack gap="sm">
        {several ? (
          <MultiSelect label="Stations this Administrator looks after" data={data} value={chosen} onChange={setChosen} searchable required />
        ) : (
          <Select label="Station" description="Works at exactly one station." data={data} value={chosen[0] ?? null} onChange={(value) => setChosen(value ? [value] : [])} required allowDeselect={false} />
        )}
        <Textarea label="Reason (kept in the history)" value={reason} onChange={(e) => setReason(e.currentTarget.value)} autosize minRows={2} maxLength={500} required />
        <Alert color="gray" variant="light" icon={<IconInfoCircle size={18} />}>
          An ended assignment is kept in the history. The person sees the cases of their stations from now on.
        </Alert>
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={chosen.length === 0 || reason.trim().length < 5} loading={mutation.isPending} onClick={() => mutation.mutate()}>
            Save stations
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}

// ------------------------------------------------------------------ register of officers

function OfficersTab({ caps }: { caps: PeopleCapabilities }) {
  const [search, setSearch] = useState('')
  const [q] = useDebouncedValue(search.trim(), 300)
  const [free, setFree] = useState(false)
  const officers = useQuery({ queryKey: ['kh', 'people', 'officers', q, free], queryFn: () => kh.officers({ q: q || undefined, free }) })
  const [adding, setAdding] = useState(false)
  const [importing, setImporting] = useState(false)
  const [making, setMaking] = useState<OfficerOut | null>(null)
  const [issued, setIssued] = useState<{ password: string; who: string } | null>(null)
  return (
    <Stack gap="sm">
      <Group justify="space-between" wrap="wrap">
        <Group>
          <TextInput placeholder="Search by officer ID or name" value={search} onChange={(e) => setSearch(e.currentTarget.value)} w={300} />
          <Switch label="Without an account" checked={free} onChange={(e) => setFree(e.currentTarget.checked)} />
        </Group>
        {caps.can_enter_officers && (
          <Group>
            <Button variant="light" leftSection={<IconFileImport size={16} />} onClick={() => setImporting(true)}>
              Import a CSV file
            </Button>
            <Button leftSection={<IconPlus size={16} />} onClick={() => setAdding(true)}>
              Add an officer
            </Button>
          </Group>
        )}
      </Group>
      <Panel p="0">
        <Loaded query={officers}>
          {(rows) =>
            rows.length === 0 ? (
              <EmptyState title="No officers">{caps.can_enter_officers ? 'Add the officers of your force, one by one or from a CSV file.' : 'The officers of your stations appear here once the Super Admin has entered them.'}</EmptyState>
            ) : (
              <Table verticalSpacing="xs" highlightOnHover>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Officer ID</Table.Th>
                    <Table.Th>Name and rank</Table.Th>
                    <Table.Th>Station</Table.Th>
                    <Table.Th>Highest role</Table.Th>
                    <Table.Th>Account</Table.Th>
                    <Table.Th />
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {rows.map((o) => (
                    <Table.Tr key={o.id}>
                      <Table.Td>
                        <Text size="sm" ff="monospace" fw={600}>
                          {o.officer_number}
                        </Text>
                      </Table.Td>
                      <Table.Td>
                        <Text size="sm">{o.full_name}</Text>
                        <Text size="xs" c="dimmed">
                          {o.rank}
                        </Text>
                      </Table.Td>
                      <Table.Td>
                        <Badge variant="outline" color="gray" size="sm">
                          {o.station.code}
                        </Badge>
                      </Table.Td>
                      <Table.Td>
                        <Text size="sm">{roleLabel(o.highest_role)}</Text>
                      </Table.Td>
                      <Table.Td>
                        {o.account ? (
                          <Text size="sm">
                            @{o.account.username} {!o.account.is_active && <Badge color="red" size="xs">ended</Badge>}
                          </Text>
                        ) : (
                          <Text size="sm" c="dimmed">
                            none yet
                          </Text>
                        )}
                      </Table.Td>
                      <Table.Td>
                        {!o.account && caps.can_create_accounts && o.creatable_roles.length > 0 && (
                          <Button size="compact-xs" variant="light" onClick={() => setMaking(o)}>
                            Create account
                          </Button>
                        )}
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            )
          }
        </Loaded>
      </Panel>
      {adding && <AddOfficerModal onClose={() => setAdding(false)} />}
      {importing && <ImportOfficersModal onClose={() => setImporting(false)} />}
      {making && <CreateAccountModal opened onClose={() => setMaking(null)} officer={making} onCreated={(password, who) => setIssued({ password, who })} />}
      <TemporaryPasswordModal issued={issued} onClose={() => setIssued(null)} />
    </Stack>
  )
}

function AddOfficerModal({ onClose }: { onClose: () => void }) {
  const refresh = useRefreshPeople()
  const stations = useQuery({ queryKey: ['kh', 'people', 'stations'], queryFn: () => kh.peopleStations() })
  const [number, setNumber] = useState('')
  const [name, setName] = useState('')
  const [rank, setRank] = useState('')
  const [station, setStation] = useState<string | null>(null)
  const [highest, setHighest] = useState<string | null>('investigator')
  const mutation = useMutation({
    mutationFn: () => kh.addOfficer({ officer_number: number.trim(), full_name: name.trim(), rank: rank.trim(), station_id: station!, highest_role: highest! }),
    onSuccess: (o) => {
      refresh()
      toastDone(`${o.officer_number} added to the register`)
      onClose()
    },
    onError: (error) => toastError(error, 'The officer was not added'),
  })
  return (
    <Modal opened onClose={onClose} title={<Text fw={600}>Add an officer to the register</Text>} size="md">
      <Stack gap="sm">
        <TextInput label="Officer ID" description="Collar, badge or service number. Each ID appears once." value={number} onChange={(e) => setNumber(e.currentTarget.value)} required />
        <TextInput label="Full name" value={name} onChange={(e) => setName(e.currentTarget.value)} required />
        <TextInput label="Rank" value={rank} onChange={(e) => setRank(e.currentTarget.value)} required />
        <Select label="Station" data={(stations.data ?? []).filter((s) => s.status === 'active').map((s) => ({ value: s.id, label: `${s.code}: ${s.name}` }))} value={station} onChange={setStation} searchable required />
        <Select
          label="Highest role an account may have"
          description="The account for this officer can be made with this role or a lower one."
          data={ALL_ROLES.map((r) => ({ value: r, label: roleLabel(r) }))}
          value={highest}
          onChange={setHighest}
          allowDeselect={false}
        />
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={number.trim().length < 2 || name.trim().length < 3 || rank.trim().length < 2 || !station || !highest} loading={mutation.isPending} onClick={() => mutation.mutate()}>
            Add officer
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}

function ImportOfficersModal({ onClose }: { onClose: () => void }) {
  const refresh = useRefreshPeople()
  const [file, setFile] = useState<File | null>(null)
  const [result, setResult] = useState<OfficerImportResult | null>(null)
  const mutation = useMutation({
    mutationFn: () => kh.importOfficers(file!),
    onSuccess: (r) => {
      setResult(r)
      if (r.imported > 0) {
        refresh()
        toastDone(`${r.imported} officers added to the register`)
      }
    },
    onError: (error) => toastError(error, 'The file was not imported'),
  })
  return (
    <Modal opened onClose={onClose} title={<Text fw={600}>Import officers from a CSV file</Text>} size="lg">
      <Stack gap="sm">
        <Text size="sm">
          The first row names the columns: <Code>officer_number, full_name, rank, station_code, highest_role</Code>. All or nothing: if any row has a problem, nothing is entered and every problem is listed.
        </Text>
        <Button component="a" variant="subtle" size="xs" href={`data:text/csv;charset=utf-8,${encodeURIComponent(CSV_TEMPLATE)}`} download="officers-template.csv" w="fit-content">
          Download a template
        </Button>
        <FileInput label="CSV file" accept=".csv,text/csv" value={file} onChange={(f) => { setFile(f); setResult(null) }} clearable />
        {result && result.imported > 0 && <Alert color="teal">{result.imported} officers were added to the register.</Alert>}
        {result && result.errors.length > 0 && (
          <Alert color="red" title="Nothing was entered. Fix these rows and try again:">
            <Stack gap={2}>
              {result.errors.map((e) => (
                <Text key={e.row} size="xs">
                  Row {e.row}{e.officer_number ? ` (${e.officer_number})` : ''}: {e.message}
                </Text>
              ))}
            </Stack>
          </Alert>
        )}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            {result && result.imported > 0 ? 'Close' : 'Cancel'}
          </Button>
          <Button disabled={!file || (result?.imported ?? 0) > 0} loading={mutation.isPending} onClick={() => mutation.mutate()}>
            Check and import
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}

// ------------------------------------------------------------------ stations

function StationsTab({ caps }: { caps: PeopleCapabilities }) {
  const stations = useQuery({ queryKey: ['kh', 'people', 'stations'], queryFn: () => kh.peopleStations() })
  const [opening, setOpening] = useState(false)
  const [editing, setEditing] = useState<StationSummary | null>(null)
  return (
    <Stack gap="sm">
      {caps.can_manage_stations && (
        <Group justify="flex-end">
          <Button leftSection={<IconPlus size={16} />} onClick={() => setOpening(true)}>
            Open a police station
          </Button>
        </Group>
      )}
      <Panel p="0">
        <Loaded query={stations}>
          {(rows) =>
            rows.length === 0 ? (
              <EmptyState title="No stations">You are not assigned to a police station yet.</EmptyState>
            ) : (
              <Table verticalSpacing="xs" highlightOnHover>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Station</Table.Th>
                    <Table.Th>District</Table.Th>
                    <Table.Th>People</Table.Th>
                    <Table.Th>Officers</Table.Th>
                    <Table.Th>Cases (open)</Table.Th>
                    <Table.Th>Status</Table.Th>
                    <Table.Th />
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {rows.map((s) => (
                    <Table.Tr key={s.id}>
                      <Table.Td>
                        <Text size="sm" fw={600} ff="monospace">
                          {s.code}
                        </Text>
                        <Text size="xs" c="dimmed">
                          {s.name}
                        </Text>
                      </Table.Td>
                      <Table.Td>{s.district ?? '—'}</Table.Td>
                      <Table.Td>{s.people}</Table.Td>
                      <Table.Td>{s.officers}</Table.Td>
                      <Table.Td>
                        {s.cases} ({s.open_cases})
                      </Table.Td>
                      <Table.Td>{s.status === 'active' ? <Badge color="green" variant="light" size="sm">active</Badge> : <Badge color="gray" size="sm">inactive</Badge>}</Table.Td>
                      <Table.Td>
                        {caps.can_manage_stations && (
                          <Button size="compact-xs" variant="subtle" onClick={() => setEditing(s)}>
                            Edit
                          </Button>
                        )}
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            )
          }
        </Loaded>
      </Panel>
      {opening && <StationModal onClose={() => setOpening(false)} />}
      {editing && <StationModal station={editing} onClose={() => setEditing(null)} />}
    </Stack>
  )
}

function StationModal({ station, onClose }: { station?: StationSummary; onClose: () => void }) {
  const refresh = useRefreshPeople()
  const [code, setCode] = useState('')
  const [name, setName] = useState(station?.name ?? '')
  const [district, setDistrict] = useState(station?.district ?? '')
  const [status, setStatus] = useState(station?.status ?? 'active')
  const mutation = useMutation({
    mutationFn: () =>
      station
        ? kh.updateStation(station.id, { name: name.trim(), district: district.trim() || null, status })
        : kh.createStation({ code: code.trim(), name: name.trim(), district: district.trim() || null }),
    onSuccess: (s) => {
      refresh()
      toastDone(station ? `${s.code} saved` : `Station ${s.code} opened`)
      onClose()
    },
    onError: (error) => toastError(error, 'The station was not saved'),
  })
  return (
    <Modal opened onClose={onClose} title={<Text fw={600}>{station ? `Station ${station.code}` : 'Open a police station'}</Text>} size="md">
      <Stack gap="sm">
        {!station && <TextInput label="Code" description="2 to 16 capital letters, digits or '-', for example PS-014. It cannot be changed later." value={code} onChange={(e) => setCode(e.currentTarget.value.toUpperCase())} required />}
        <TextInput label="Name" value={name} onChange={(e) => setName(e.currentTarget.value)} required />
        <TextInput label="District" value={district} onChange={(e) => setDistrict(e.currentTarget.value)} />
        {station && (
          <Select
            label="Status"
            description="An inactive station keeps its cases and history; no new case can be registered there."
            data={[{ value: 'active', label: 'Active' }, { value: 'inactive', label: 'Inactive' }]}
            value={status}
            onChange={(value) => setStatus(value ?? 'active')}
            allowDeselect={false}
          />
        )}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={(!station && code.trim().length < 2) || name.trim().length < 3} loading={mutation.isPending} onClick={() => mutation.mutate()}>
            {station ? 'Save' : 'Open station'}
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}
