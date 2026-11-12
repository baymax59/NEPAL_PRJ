import { Mark, Text } from '@mantine/core'
import type { SnippetPart } from '../api/types'

/**
 * A passage with the search words highlighted.
 *
 * The backend sends plain-text parts; each is rendered as text, never as HTML, so nothing
 * inside a judgment (or an uploaded document) can inject markup or scripts into the page.
 */
export function SnippetText({ parts, size = 'sm' }: { parts: SnippetPart[]; size?: string }) {
  return (
    <Text size={size} component="span">
      {parts.map((part, index) =>
        part.match ? (
          <Mark key={index} color="yellow">
            {part.text}
          </Mark>
        ) : (
          <span key={index}>{part.text}</span>
        ),
      )}
    </Text>
  )
}
