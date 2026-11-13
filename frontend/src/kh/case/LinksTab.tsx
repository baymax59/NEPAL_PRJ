// Case links and relationship graph (spec §21 screen 18).

import { Anchor, Badge, Box, Button, Group, Modal, Paper, Select, SimpleGrid, Stack, Table, Text, Textarea, useComputedColorScheme } from '@mantine/core'
import { useDebouncedValue } from '@mantine/hooks'
import { IconArrowBackUp, IconLink, IconPlus } from '@tabler/icons-react'
import { Background, Controls, Handle, Position, ReactFlow, type Edge, type Node, type NodeProps } from '@xyflow/react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import { kh } from '../api'
import type { CaseDetail, CaseLinks } from '../types'
import { ConfirmModal, EmptyState, Loaded, Panel, PersonName, When } from '../ui'
import { toastDone, toastError, useOnceKey } from '../feedback'
import { useCase } from './context'
import { useRefreshCase } from './helpers'

type CaseNodeData = { title: string; subtitle: string; center?: boolean; muted?: boolean; href?: string }

function CaseNode({ data }: NodeProps<Node<CaseNodeData>>) {
  return (
    <div
      style={{
        width: 190,
        padding: '6px 10px',
        borderRadius: 6,
        background: data.center ? 'var(--mantine-color-hawk-light)' : 'var(--mantine-color-default)',
        border: `${data.center ? 2 : 1}px solid ${data.center ? 'var(--mantine-color-hawk-4)' : 'var(--mantine-color-default-border)'}`,
        opacity: data.muted ? 0.6 : 1,
        cursor: data.href ? 'pointer' : 'default',
        textAlign: 'center',
      }}
    >
      <Handle type="target" position={Position.Top} style={{ opacity: 0, top: '50%' }} isConnectable={false} />
      <div style={{ fontFamily: 'var(--mantine-font-family-monospace)', fontWeight: 700, fontSize: 12, color: 'var(--mantine-color-text)' }}>{data.title}</div>
      <div style={{ fontSize: 10, color: 'var(--mantine-color-dimmed)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{data.subtitle}</div>
      <Handle type="source" position={Position.Bottom} style={{ opacity: 0, top: '50%' }} isConnectable={false} />
    </div>
  )
}
const nodeTypes = { case: CaseNode }

function RelationshipGraph({ links }: { links: CaseLinks }) {
  const navigate = useNavigate()
  const scheme = useComputedColorScheme('dark')
  const { nodes, edges } = useMemo(() => {
    const outgoing = links.outgoing.filter((l) => l.status === 'active')
    const others = [
      ...outgoing.map((l) => {
        const past = l.knowledge_case
        return {
          key: `out:${l.link_id}`,
          title: past ? past.display_id : (l.target.display_id ?? '?'),
          subtitle: past ? `Past case · ${past.title ?? ''}` : (l.target_now?.title ?? l.target.title ?? ''),
          href: past ? (l.knowledge_visible ? `/cases/${encodeURIComponent(past.display_id)}` : undefined) : l.target_now ? `/kh/case/${l.target_now.id}` : undefined,
          label: l.label,
          incoming: false,
          past: Boolean(past),
          muted: past ? !l.knowledge_visible : !l.target_now,
        }
      }),
      ...links.incoming.map((l, i) => ({
        key: `in:${i}:${l.case.id}`,
        title: l.case.display_id,
        subtitle: l.case.title,
        href: `/kh/case/${l.case.id}`,
        label: l.label,
        incoming: true,
        past: false,
        muted: false,
      })),
    ]
    const radius = Math.max(220, others.length * 42)
    const nodes: Node[] = [
      { id: 'center', type: 'case', position: { x: 0, y: 0 }, data: { title: links.case.display_id, subtitle: links.case.title, center: true }, draggable: false },
      ...others.map((o, i) => {
        const angle = (2 * Math.PI * i) / Math.max(others.length, 1) - Math.PI / 2
        return {
          id: o.key,
          type: 'case',
          position: { x: Math.cos(angle) * radius, y: Math.sin(angle) * radius * 0.6 },
          data: { title: o.title, subtitle: o.subtitle, href: o.href, muted: o.muted },
          draggable: false,
        }
      }),
    ]
    const edges: Edge[] = others.map((o) => ({
      id: `e:${o.key}`,
      source: o.incoming ? o.key : 'center',
      target: o.incoming ? 'center' : o.key,
      label: o.label,
      type: 'straight',
      animated: false,
      style: {
        stroke: o.incoming ? 'var(--mantine-color-grape-5)' : o.past ? 'var(--mantine-color-teal-5)' : 'var(--mantine-color-hawk-4)',
        strokeWidth: 2,
        strokeDasharray: o.muted ? '5 4' : undefined,
      },
      labelStyle: { fontSize: 10, fill: 'var(--mantine-color-text)' },
      labelBgStyle: { fill: 'var(--mantine-color-body)' },
    }))
    return { nodes, edges }
  }, [links])
  return (
    <Box h={380} style={{ border: '1px solid var(--mantine-color-default-border)', borderRadius: 4 }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        colorMode={scheme}
        fitView
        fitViewOptions={{ padding: 0.2, maxZoom: 1.1 }}
        nodesConnectable={false}
        onNodeClick={(_, node) => {
          const href = (node.data as CaseNodeData).href
          if (href) navigate(href)
        }}
      >
        <Background gap={24} size={1} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </Box>
  )
}

export function LinksTab() {
  const detail = useCase()
  const refresh = useRefreshCase(detail.id)
  const [linking, setLinking] = useState(false)
  const [withdrawing, setWithdrawing] = useState<{ artifactId: string; label: string } | null>(null)
  const query = useQuery({ queryKey: ['kh', 'case', detail.id, 'links'], queryFn: () => kh.links(detail.id) })
  const writable = detail.can.add_files
  const withdraw = useMutation({
    mutationFn: ({ artifactId, reason }: { artifactId: string; reason: string }) => kh.withdrawNote(artifactId, reason),
    onSuccess: () => {
      toastDone('Link withdrawn; it stays in the history')
      refresh()
      setWithdrawing(null)
    },
    onError: (error) => toastError(error),
  })
  return (
    <Stack gap="sm">
      <Group justify="space-between">
        <Text size="sm" c="dimmed">
          Cases that share a person, a method, an account or a place with this one.
        </Text>
        {writable && (
          <Button size="xs" leftSection={<IconPlus size={14} />} onClick={() => setLinking(true)}>
            Link a case
          </Button>
        )}
      </Group>
      <Loaded query={query}>
        {(links) => (
          <Stack gap="md">
            {links.outgoing.length + links.incoming.length === 0 ? (
              <Paper withBorder>
                <EmptyState title="No linked cases" icon={<IconLink size={22} />}>
                  Link cases that share a person, a method, an account or a place. Each link has a reason and is kept in the case's history.
                </EmptyState>
              </Paper>
            ) : (
              <RelationshipGraph links={links} />
            )}
            <SimpleGrid cols={{ base: 1, lg: 2 }}>
              <Panel title={`This case links to (${links.outgoing.filter((l) => l.status === 'active').length})`} p="0">
                {links.outgoing.length === 0 ? (
                  <Text size="sm" c="dimmed" p="sm">
                    Nothing yet.
                  </Text>
                ) : (
                  <Table>
                    <Table.Tbody>
                      {links.outgoing.map((l) => (
                        <Table.Tr key={l.link_id} style={{ opacity: l.status === 'active' ? 1 : 0.55 }}>
                          <Table.Td>
                            <Group gap={6}>
                              {l.knowledge_case ? (
                                l.knowledge_visible ? (
                                  <Anchor component={Link} to={`/cases/${encodeURIComponent(l.knowledge_case.display_id)}`} ff="monospace" size="sm" fw={600}>
                                    {l.knowledge_case.display_id}
                                  </Anchor>
                                ) : (
                                  <Text ff="monospace" size="sm" fw={600}>
                                    {l.knowledge_case.display_id}
                                  </Text>
                                )
                              ) : l.target_now ? (
                                <Anchor component={Link} to={`/kh/case/${l.target_now.id}`} ff="monospace" size="sm" fw={600}>
                                  {l.target.display_id}
                                </Anchor>
                              ) : (
                                <Text ff="monospace" size="sm" fw={600}>
                                  {l.target.display_id}
                                </Text>
                              )}
                              {l.knowledge_case && (
                                <Badge size="xs" variant="outline" color="teal">
                                  past case
                                </Badge>
                              )}
                              <Badge size="xs" color="hawk">
                                {l.label}
                              </Badge>
                              {l.status !== 'active' && (
                                <Badge size="xs" color="orange" variant="outline">
                                  withdrawn
                                </Badge>
                              )}
                            </Group>
                            <Text size="xs">
                              {l.knowledge_case
                                ? [l.knowledge_case.title, l.knowledge_case.court, l.knowledge_case.decision_date].filter(Boolean).join(' · ')
                                : (l.target_now?.title ?? l.target.title)}
                            </Text>
                            <Text size="xs" c="dimmed">
                              “{l.reason}”
                            </Text>
                            {!l.knowledge_case && !l.target_now && (
                              <Text size="xs" c="dimmed" fs="italic">
                                As recorded; you can't open that case.
                              </Text>
                            )}
                            {l.withdrawn_reason && (
                              <Text size="xs" c="orange">
                                Withdrawn: {l.withdrawn_reason}
                              </Text>
                            )}
                          </Table.Td>
                          <Table.Td>
                            <Stack gap={2} align="flex-end">
                              <PersonName person={l.created_by} size="xs" />
                              <When at={l.created_at} size="xs" />
                              <Text size="xs" c="dimmed" ff="monospace">
                                {l.display_id}
                              </Text>
                              {writable && l.status === 'active' && (
                                <Button size="compact-xs" variant="subtle" color="orange" leftSection={<IconArrowBackUp size={12} />} onClick={() => setWithdrawing({ artifactId: l.artifact_id, label: l.knowledge_case?.display_id ?? l.target.display_id ?? l.display_id })}>
                                  Withdraw
                                </Button>
                              )}
                            </Stack>
                          </Table.Td>
                        </Table.Tr>
                      ))}
                    </Table.Tbody>
                  </Table>
                )}
              </Panel>
              <Panel title={`Cases that link to this one (${links.incoming.length})`} p="0">
                {links.incoming.length === 0 ? (
                  <Text size="sm" c="dimmed" p="sm">
                    None that you can open.
                  </Text>
                ) : (
                  <Table>
                    <Table.Tbody>
                      {links.incoming.map((l, i) => (
                        <Table.Tr key={i}>
                          <Table.Td>
                            <Group gap={6}>
                              <Anchor component={Link} to={`/kh/case/${l.case.id}`} ff="monospace" size="sm" fw={600}>
                                {l.case.display_id}
                              </Anchor>
                              <Badge size="xs" color="grape">
                                {l.label}
                              </Badge>
                            </Group>
                            <Text size="xs">{l.case.title}</Text>
                            <Text size="xs" c="dimmed">
                              “{l.reason}”
                            </Text>
                          </Table.Td>
                          <Table.Td>
                            <Stack gap={2} align="flex-end">
                              <PersonName person={l.created_by} size="xs" />
                              <When at={l.created_at} size="xs" />
                            </Stack>
                          </Table.Td>
                        </Table.Tr>
                      ))}
                    </Table.Tbody>
                  </Table>
                )}
              </Panel>
            </SimpleGrid>
            {linking && <PickCaseDialog opened onClose={() => setLinking(false)} detail={detail} linkTypes={links.link_types} />}
          </Stack>
        )}
      </Loaded>
      <ConfirmModal
        opened={withdrawing !== null}
        onClose={() => setWithdrawing(null)}
        title={`Withdraw the link to ${withdrawing?.label}?`}
        confirmLabel="Withdraw link"
        color="orange"
        reason="required"
        loading={withdraw.isPending}
        onConfirm={(reason) => withdrawing && withdraw.mutate({ artifactId: withdrawing.artifactId, reason })}
      >
        <Text size="sm">The link leaves the current view of the case. The link, its reason and who made it stay in the history.</Text>
      </ConfirmModal>
    </Stack>
  )
}

function PickCaseDialog({ opened, onClose, detail, linkTypes }: { opened: boolean; onClose: () => void; detail: CaseDetail; linkTypes: { code: string; label: string }[] }) {
  const refresh = useRefreshCase(detail.id)
  const [key, renew] = useOnceKey()
  const [search, setSearch] = useState('')
  const [debounced] = useDebouncedValue(search, 250)
  const [target, setTarget] = useState<string | null>(null)
  const [type, setType] = useState<string | null>(linkTypes[0]?.code ?? null)
  const [reason, setReason] = useState('')
  const cases = useQuery({ queryKey: ['kh', 'cases', 'search', debounced], queryFn: () => kh.cases({ q: debounced || undefined, limit: 20 }) })
  const options = (cases.data?.items ?? []).filter((c) => c.id !== detail.id)
  const mutation = useMutation({
    mutationFn: () => kh.addLink(detail.id, { target_case_id: target!, link_type: type as 'related', reason: reason.trim() }, key),
    onSuccess: () => {
      renew()
      refresh()
      toastDone('Case linked')
      onClose()
    },
    onError: (error) => toastError(error, 'Not linked'),
  })
  return (
    <Modal opened={opened} onClose={onClose} size="lg" title={<Text fw={600}>Link a case to {detail.display_id}</Text>}>
      <Stack gap="sm">
        <Select
          label="Case"
          description="Cases you can open. Type an ID or words from the title."
          searchable
          searchValue={search}
          onSearchChange={setSearch}
          filter={({ options: all }) => all}
          data={options.map((c) => ({ value: c.id, label: `${c.display_id} · ${c.title}` }))}
          value={target}
          onChange={setTarget}
          nothingFoundMessage={cases.isFetching ? 'Searching…' : 'No case found'}
          required
        />
        <Select label="How are they related?" data={linkTypes.map((t) => ({ value: t.code, label: t.label }))} value={type} onChange={setType} allowDeselect={false} />
        <Textarea label="Reason" description="At least 10 characters; it stays with the link." value={reason} onChange={(e) => setReason(e.currentTarget.value)} autosize minRows={3} maxLength={1000} required />
        <Text size="xs" c="dimmed">
          The link is added to the case at once and stays in the history even if it is withdrawn later. To link a past case of the knowledge base, use Insights → Similar cases.
        </Text>
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={!target || !type || reason.trim().length < 10} loading={mutation.isPending} onClick={() => mutation.mutate()} leftSection={<IconLink size={16} />}>
            Link
          </Button>
        </Group>
      </Stack>
    </Modal>
  )
}
