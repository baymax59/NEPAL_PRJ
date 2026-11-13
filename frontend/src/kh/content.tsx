// Showing what a note or analysis contains, and what changed between two versions.

import { Box, Code, Group, ScrollArea, Stack, Table, Text } from '@mantine/core'
import { contentText, diffLines, type DiffLine } from './diff'
import { humanize } from './labels'

type Content = Record<string, unknown> | null | undefined


export function ContentView({ content }: { content: Content }) {
  if (!content) {
    return (
      <Text size="sm" c="dimmed">
        No content.
      </Text>
    )
  }
  const keys = Object.keys(content)
  if (typeof content.text === 'string' && keys.length === 1) {
    return (
      <Text size="sm" style={{ whiteSpace: 'pre-wrap', lineHeight: 1.6 }}>
        {content.text}
      </Text>
    )
  }
  // A structured record (e.g. the case information note): one row per field.
  return (
    <Table withRowBorders={false} verticalSpacing={4}>
      <Table.Tbody>
        {keys.map((key) => (
          <Table.Tr key={key}>
            <Table.Td w={200} valign="top">
              <Text size="xs" c="dimmed">
                {humanize(key)}
              </Text>
            </Table.Td>
            <Table.Td>
              <Value value={content[key]} />
            </Table.Td>
          </Table.Tr>
        ))}
      </Table.Tbody>
    </Table>
  )
}

function Value({ value }: { value: unknown }) {
  if (value === null || value === undefined || value === '') return <Text span size="sm" c="dimmed">—</Text>
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return (
      <Text span size="sm" style={{ whiteSpace: 'pre-wrap' }}>
        {String(value)}
      </Text>
    )
  }
  return (
    <Code block fz="xs">
      {JSON.stringify(value, null, 2)}
    </Code>
  )
}

// ------------------------------------------------------------------ line differences



const LINE_STYLE: Record<DiffLine['kind'], { bg: string; sign: string; color?: string }> = {
  same: { bg: 'transparent', sign: ' ' },
  added: { bg: 'var(--mantine-color-green-light)', sign: '+', color: 'var(--mantine-color-green-light-color)' },
  removed: { bg: 'var(--mantine-color-red-light)', sign: '−', color: 'var(--mantine-color-red-light-color)' },
}

/** A read-only comparison of two versions (spec §3: "a suitable read-only comparison component"). */
export function DiffView({ before, after, maxHeight = 420 }: { before: Content; after: Content; maxHeight?: number }) {
  const lines = diffLines(contentText(before), contentText(after))
  const added = lines.filter((l) => l.kind === 'added').length
  const removed = lines.filter((l) => l.kind === 'removed').length
  return (
    <Stack gap={4}>
      <Group gap="xs">
        <Text size="xs" c="green">
          +{added}
        </Text>
        <Text size="xs" c="red">
          −{removed}
        </Text>
        <Text size="xs" c="dimmed">
          lines
        </Text>
      </Group>
      <ScrollArea.Autosize mah={maxHeight} type="auto">
        <Box
          component="pre"
          m={0}
          ff="monospace"
          fz="xs"
          style={{ border: '1px solid var(--mantine-color-default-border)', borderRadius: 4, overflowX: 'auto' }}
        >
          {lines.length === 0 && (
            <Text size="xs" c="dimmed" p="xs">
              Both versions are empty.
            </Text>
          )}
          {lines.map((line, index) => {
            const style = LINE_STYLE[line.kind]
            return (
              <Box key={index} style={{ background: style.bg, display: 'flex', minWidth: 'fit-content' }}>
                <Box component="span" c="dimmed" w={34} ta="right" pr={6} style={{ flex: 'none', userSelect: 'none' }}>
                  {line.before ?? ''}
                </Box>
                <Box component="span" c="dimmed" w={34} ta="right" pr={6} style={{ flex: 'none', userSelect: 'none' }}>
                  {line.after ?? ''}
                </Box>
                <Box component="span" w={16} style={{ flex: 'none', color: style.color, userSelect: 'none' }}>
                  {style.sign}
                </Box>
                <Box component="span" style={{ color: style.color, whiteSpace: 'pre' }}>
                  {line.text || ' '}
                </Box>
              </Box>
            )
          })}
        </Box>
      </ScrollArea.Autosize>
    </Stack>
  )
}
