import { Group, Text } from '@mantine/core'

/** The Knight Hawk mark: a hawk with spread wings inside a shield (an original drawing). */
export function HawkMark({ size = 26, color = 'var(--mantine-color-hawk-4)' }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" role="img" aria-label="Knight Hawk" style={{ color, flex: 'none' }}>
      <path d="M16 2.5 27.5 7v8.2c0 7-4.9 12.3-11.5 14.3C9.4 27.5 4.5 22.2 4.5 15.2V7Z" fill="none" stroke="currentColor" strokeWidth="2" />
      <path d="M8.5 13.6 16 10.2l7.5 3.4-4.1 1.2L16 20.5l-3.4-5.7Z" fill="currentColor" />
      <circle cx="16" cy="12.9" r="1.1" fill="var(--mantine-color-body)" />
    </svg>
  )
}

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <Group gap={8} wrap="nowrap">
      <HawkMark />
      {!compact && (
        <div>
          <Text fw={800} size="sm" lh={1.1} style={{ letterSpacing: 1.2 }}>
            KNIGHT HAWK
          </Text>
          <Text size="10px" c="dimmed" lh={1.1} style={{ letterSpacing: 0.4 }}>
            Case Management
          </Text>
        </div>
      )}
    </Group>
  )
}
