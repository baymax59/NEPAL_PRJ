// CDR call graph using @xyflow/react.

import { Background, BackgroundVariant, Controls, Handle, MiniMap, Position, ReactFlow, type NodeProps } from '@xyflow/react'
import { Alert, Box, Group, Paper, Slider, Stack, Text } from '@mantine/core'
import { IconAlertTriangle } from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { kh } from '../../api'
import type { CdrGraphEdge, CdrGraphNode } from '../../types'

interface Props {
  caseId: string
}

const MAX_NODES = 150

function PhoneNode({ data }: NodeProps) {
  return (
    <Box
      px={8}
      py={4}
      style={{
        background: 'var(--mantine-color-hawk-1)',
        border: '1px solid var(--mantine-color-hawk-4)',
        borderRadius: 6,
        fontSize: 10,
        fontFamily: 'monospace',
        maxWidth: 160,
        whiteSpace: 'nowrap',
        overflow: 'hidden',
        textOverflow: 'ellipsis',
      }}
    >
      <Handle type="target" position={Position.Left} />
      <span title={String(data.label)}>{String(data.label)}</span>
      <Handle type="source" position={Position.Right} />
    </Box>
  )
}

const nodeTypes = { phone: PhoneNode }

function buildFlow(nodes: CdrGraphNode[], edges: CdrGraphEdge[]) {
  const cols = Math.ceil(Math.sqrt(nodes.length))
  const flowNodes = nodes.map((n, i) => ({
    id: n.id,
    type: 'phone' as const,
    position: { x: (i % cols) * 200, y: Math.floor(i / cols) * 80 },
    data: { label: n.label },
  }))
  const maxCount = Math.max(...edges.map((e) => e.count), 1)
  const flowEdges = edges.map((e) => ({
    id: `${e.source}->${e.target}`,
    source: e.source,
    target: e.target,
    label: `${e.count}`,
    style: {
      strokeWidth: 1 + Math.round((e.count / maxCount) * 4),
      stroke: 'var(--mantine-color-hawk-5)',
    },
    labelStyle: { fontSize: 9 },
  }))
  return { flowNodes, flowEdges }
}

export function CdrCallGraphPanel({ caseId }: Props) {
  const [minCalls, setMinCalls] = useState(1)

  const query = useQuery({
    queryKey: ['kh', 'case', caseId, 'cdr', 'call-graph', minCalls],
    queryFn: () => kh.cdrCallGraph(caseId, minCalls),
  })

  const { flowNodes, flowEdges } = useMemo(() => {
    if (!query.data) return { flowNodes: [], flowEdges: [] }
    return buildFlow(query.data.nodes.slice(0, MAX_NODES), query.data.edges)
  }, [query.data])

  const tooMany = (query.data?.nodes.length ?? 0) > MAX_NODES

  if (query.isPending) {
    return <Text size="sm" c="dimmed">Loading call graph…</Text>
  }

  if (query.isError) {
    return <Text size="sm" c="red">Could not load the call graph.</Text>
  }

  const { nodes, edges } = query.data!

  if (nodes.length === 0) {
    return (
      <Paper withBorder p="lg" radius="sm" ta="center">
        <Text size="sm" c="dimmed">No connections to show. Try lowering the minimum calls filter.</Text>
      </Paper>
    )
  }

  return (
    <Stack gap="sm">
      <Group gap="xl" wrap="wrap" align="flex-end">
        <Box style={{ flex: 1, minWidth: 200 }}>
          <Text size="xs" fw={500} mb={4}>Minimum calls between numbers: {minCalls}</Text>
          <Slider
            value={minCalls}
            onChange={setMinCalls}
            min={1}
            max={20}
            step={1}
            label={(v) => `${v}`}
            marks={[{ value: 1, label: '1' }, { value: 10, label: '10' }, { value: 20, label: '20' }]}
          />
        </Box>
        <Text size="xs" c="dimmed">{nodes.length} nodes · {edges.length} edges</Text>
      </Group>

      {tooMany && (
        <Alert color="yellow" icon={<IconAlertTriangle size={16} />} p="xs">
          <Text size="sm">Only the first {MAX_NODES} nodes are shown. Increase the minimum calls to narrow the graph.</Text>
        </Alert>
      )}

      <Paper withBorder radius="sm" style={{ height: 500, overflow: 'hidden' }}>
        <ReactFlow
          nodes={flowNodes}
          edges={flowEdges}
          nodeTypes={nodeTypes}
          fitView
          minZoom={0.1}
          maxZoom={2}
          proOptions={{ hideAttribution: true }}
        >
          <Background variant={BackgroundVariant.Dots} gap={16} size={1} />
          <Controls />
          <MiniMap zoomable pannable />
        </ReactFlow>
      </Paper>
    </Stack>
  )
}
