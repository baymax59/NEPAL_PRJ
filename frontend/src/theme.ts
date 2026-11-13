import { createTheme, type MantineColorsTuple } from '@mantine/core'

// Knight Hawk: a dark navy base with restrained cyan accents (spec §21). Colours were chosen for contrast:
// body text on the navy background is about 14:1 and dimmed text about 6:1 (WCAG AA needs 4.5:1).

/** The accent: a clear cyan-blue. Filled buttons use dark text on it (autoContrast). */
const hawk: MantineColorsTuple = [
  '#e1f8ff',
  '#cbedff',
  '#9ad8ff',
  '#64c2ff',
  '#3aafff',
  '#22a4ff',
  '#0b9df8',
  '#0089dd',
  '#0079c6',
  '#0068af',
]

/** Mantine's "dark" scale, re-tinted navy: 0 = text, 2 = dimmed text, 4 = borders, 6 = surfaces, 7 = page. */
const navy: MantineColorsTuple = [
  '#dbe2ee',
  '#b8c3d6',
  '#8f9cb6',
  '#5f6c89',
  '#2b3956',
  '#1d2943',
  '#152037',
  '#0d1628',
  '#09111f',
  '#050a14',
]

export const theme = createTheme({
  primaryColor: 'hawk',
  // Filled buttons use the same deep shade in both schemes: white text on it is 4.6:1 (WCAG AA). Mantine picks
  // the text colour from the light shade, so a brighter dark-mode shade would get unreadable white text.
  // Links keep the bright shade 4 in dark mode (Mantine's anchor colour), about 7:1 on the navy page.
  primaryShade: { light: 8, dark: 8 },
  autoContrast: true,
  colors: { hawk, dark: navy },
  defaultRadius: 'sm',
  fontFamily: '"Plus Jakarta Sans", "Segoe UI", system-ui, -apple-system, Roboto, "Noto Sans", "Helvetica Neue", Arial, sans-serif',
  fontFamilyMonospace: '"Cascadia Mono", "JetBrains Mono", Consolas, "SFMono-Regular", Menlo, "Liberation Mono", monospace',
  headings: { fontFamily: '"Plus Jakarta Sans", "Segoe UI", system-ui, -apple-system, Roboto, "Noto Sans", "Helvetica Neue", Arial, sans-serif', fontWeight: '600' },
  components: {
    Badge: { defaultProps: { radius: 'sm', variant: 'light' } },
    Table: { defaultProps: { verticalSpacing: 6, horizontalSpacing: 'sm', fz: 'sm', highlightOnHover: true } },
    Tooltip: { defaultProps: { withArrow: true, openDelay: 250 } },
    Modal: { defaultProps: { centered: true, overlayProps: { backgroundOpacity: 0.6, blur: 2 } } },
  },
})
