// The description of a case is written with a formatting toolbar (like an email) and shown the way it was written.
// The server cleans the styled copy before storing it (backend/app/casemgmt/rich_text.py); it is cleaned once more here before it is shown.

import { ActionIcon, ColorPicker, Divider, Group, Menu, Popover, Stack, Text, Tooltip, UnstyledButton } from '@mantine/core'
import {
  IconAlignCenter,
  IconAlignJustified,
  IconAlignLeft,
  IconAlignRight,
  IconArrowBackUp,
  IconArrowForwardUp,
  IconBold,
  IconCheck,
  IconChevronDown,
  IconClearFormatting,
  IconDotsVertical,
  IconItalic,
  IconList,
  IconListNumbers,
  IconTextSize,
  IconUnderline,
} from '@tabler/icons-react'
import TextAlign from '@tiptap/extension-text-align'
import { Color, FontFamily, FontSize, TextStyle } from '@tiptap/extension-text-style'
import { EditorContent, useEditor, useEditorState } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import DOMPurify from 'dompurify'
import { useMemo } from 'react'
import type { ReactNode } from 'react'

const FONTS: { label: string; value: string | null }[] = [
  { label: 'Sans Serif', value: null },
  { label: 'Serif', value: 'Times New Roman, serif' },
  { label: 'Fixed width', value: 'Courier New, monospace' },
  { label: 'Wide', value: 'Arial Black, sans-serif' },
  { label: 'Narrow', value: 'Arial Narrow, sans-serif' },
  { label: 'Comic Sans MS', value: 'Comic Sans MS, cursive' },
  { label: 'Garamond', value: 'Garamond, serif' },
  { label: 'Georgia', value: 'Georgia, serif' },
  { label: 'Tahoma', value: 'Tahoma, sans-serif' },
  { label: 'Trebuchet MS', value: 'Trebuchet MS, sans-serif' },
  { label: 'Verdana', value: 'Verdana, sans-serif' },
]
const SIZES: { label: string; value: string | null; px: number }[] = [
  { label: 'Small', value: '12px', px: 12 },
  { label: 'Normal', value: null, px: 14 },
  { label: 'Large', value: '20px', px: 20 },
  { label: 'Huge', value: '28px', px: 28 },
]
const COLORS = [
  '#000000', '#434343', '#666666', '#999999', '#cccccc', '#efefef', '#ffffff',
  '#c92a2a', '#e8590c', '#f08c00', '#2f9e44', '#1971c2', '#6741d9', '#c2255c',
  '#ffa8a8', '#ffc078', '#ffe066', '#8ce99a', '#74c0fc', '#b197fc', '#faa2c1',
]
const ALIGNS = [
  { value: 'left', label: 'Align left', icon: IconAlignLeft },
  { value: 'center', label: 'Align centre', icon: IconAlignCenter },
  { value: 'right', label: 'Align right', icon: IconAlignRight },
  { value: 'justify', label: 'Justify', icon: IconAlignJustified },
] as const

// Pressing a toolbar button must not take the cursor out of the text.
const keepSelection = (e: { preventDefault: () => void }) => e.preventDefault()

function Tool({ label, active, disabled, onClick, children }: { label: string; active?: boolean; disabled?: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <Tooltip label={label} openDelay={400} withArrow>
      <ActionIcon
        variant={active ? 'light' : 'subtle'}
        color={active ? 'blue' : 'gray'}
        size="lg"
        radius="xl"
        aria-label={label}
        aria-pressed={active}
        disabled={disabled}
        onMouseDown={keepSelection}
        onClick={onClick}
      >
        {children}
      </ActionIcon>
    </Tooltip>
  )
}

const Separator = () => <Divider orientation="vertical" h={20} mx={4} my="auto" />

export function RichTextEditor({ initial, onChange }: { initial: string; onChange: (html: string, text: string) => void }) {
  const editor = useEditor({
    extensions: [
      StarterKit.configure({ heading: false, blockquote: false, codeBlock: false, code: false, horizontalRule: false, link: false, strike: false }),
      TextStyle,
      Color,
      FontFamily,
      FontSize,
      TextAlign.configure({ types: ['paragraph'] }),
    ],
    content: initial,
    autofocus: 'end',
    editorProps: { attributes: { role: 'textbox', 'aria-label': 'Description', 'aria-multiline': 'true' } },
    onUpdate: ({ editor: e }) => onChange(e.getHTML(), e.getText({ blockSeparator: '\n' })),
  })
  const now = useEditorState({
    editor,
    selector: ({ editor: e }) => ({
      bold: e?.isActive('bold') ?? false,
      italic: e?.isActive('italic') ?? false,
      underline: e?.isActive('underline') ?? false,
      numbered: e?.isActive('orderedList') ?? false,
      bullets: e?.isActive('bulletList') ?? false,
      canUndo: e?.can().undo() ?? false,
      canRedo: e?.can().redo() ?? false,
      font: (e?.getAttributes('textStyle').fontFamily as string | undefined) ?? null,
      size: (e?.getAttributes('textStyle').fontSize as string | undefined) ?? null,
      color: (e?.getAttributes('textStyle').color as string | undefined) ?? null,
      align: (['center', 'right', 'justify'].find((a) => e?.isActive({ textAlign: a })) ?? 'left') as 'left' | 'center' | 'right' | 'justify',
    }),
  })
  if (!editor || !now) return null
  const chain = () => editor.chain().focus()
  const fontLabel = FONTS.find((f) => f.value === now.font)?.label ?? 'Sans Serif'
  const AlignIcon = ALIGNS.find((a) => a.value === now.align)?.icon ?? IconAlignLeft

  return (
    <Stack gap={0}>
      <Group
        gap={2}
        wrap="nowrap"
        px="sm"
        py={4}
        mx="sm"
        my={8}
        bg="var(--mantine-color-default-hover)"
        style={{ borderRadius: 999, overflowX: 'auto' }}
        role="toolbar"
        aria-label="Text formatting"
      >
        <Tool label="Undo" disabled={!now.canUndo} onClick={() => chain().undo().run()}>
          <IconArrowBackUp size={18} />
        </Tool>
        <Tool label="Redo" disabled={!now.canRedo} onClick={() => chain().redo().run()}>
          <IconArrowForwardUp size={18} />
        </Tool>
        <Separator />
        <Menu withinPortal position="bottom-start" shadow="md">
          <Menu.Target>
            <UnstyledButton onMouseDown={keepSelection} aria-label="Font" px="xs" py={4} style={{ borderRadius: 999, whiteSpace: 'nowrap', width: 120 }}>
              <Group gap={4} justify="space-between" wrap="nowrap">
                <Text size="sm" truncate>
                  {fontLabel}
                </Text>
                <IconChevronDown size={14} />
              </Group>
            </UnstyledButton>
          </Menu.Target>
          <Menu.Dropdown>
            {FONTS.map((f) => (
              <Menu.Item
                key={f.label}
                onMouseDown={keepSelection}
                rightSection={f.value === now.font ? <IconCheck size={14} /> : null}
                style={{ fontFamily: f.value ?? 'inherit' }}
                onClick={() => (f.value ? chain().setFontFamily(f.value).run() : chain().unsetFontFamily().run())}
              >
                {f.label}
              </Menu.Item>
            ))}
          </Menu.Dropdown>
        </Menu>
        <Separator />
        <Menu withinPortal position="bottom-start" shadow="md">
          <Menu.Target>
            <ActionIcon variant="subtle" color="gray" size="lg" radius="xl" aria-label="Text size" onMouseDown={keepSelection} w={48}>
              <IconTextSize size={20} />
              <IconChevronDown size={12} />
            </ActionIcon>
          </Menu.Target>
          <Menu.Dropdown>
            {SIZES.map((sz) => (
              <Menu.Item
                key={sz.label}
                onMouseDown={keepSelection}
                rightSection={sz.value === now.size ? <IconCheck size={14} /> : null}
                style={{ fontSize: sz.px }}
                onClick={() => (sz.value ? chain().setFontSize(sz.value).run() : chain().unsetFontSize().run())}
              >
                {sz.label}
              </Menu.Item>
            ))}
          </Menu.Dropdown>
        </Menu>
        <Separator />
        <Tool label="Bold" active={now.bold} onClick={() => chain().toggleBold().run()}>
          <IconBold size={18} />
        </Tool>
        <Tool label="Italic" active={now.italic} onClick={() => chain().toggleItalic().run()}>
          <IconItalic size={18} />
        </Tool>
        <Tool label="Underline" active={now.underline} onClick={() => chain().toggleUnderline().run()}>
          <IconUnderline size={18} />
        </Tool>
        <Popover withinPortal position="bottom" shadow="md" withArrow>
          <Popover.Target>
            <ActionIcon variant="subtle" color="gray" size="lg" radius="xl" aria-label="Text colour" onMouseDown={keepSelection} w={48}>
              <Stack gap={0} align="center">
                <Text fw={700} size="sm" lh={1}>
                  A
                </Text>
                <span style={{ width: 14, height: 3, background: now.color ?? 'currentColor', borderRadius: 2 }} />
              </Stack>
              <IconChevronDown size={12} />
            </ActionIcon>
          </Popover.Target>
          <Popover.Dropdown p="xs">
            <ColorPicker format="hex" withPicker={false} swatches={COLORS} swatchesPerRow={7} value={now.color ?? ''} onChange={(c) => chain().setColor(c).run()} />
            <UnstyledButton mt={6} onMouseDown={keepSelection} onClick={() => chain().unsetColor().run()}>
              <Text size="xs" c="dimmed">
                Default colour
              </Text>
            </UnstyledButton>
          </Popover.Dropdown>
        </Popover>
        <Separator />
        <Menu withinPortal position="bottom-start" shadow="md">
          <Menu.Target>
            <ActionIcon variant="subtle" color="gray" size="lg" radius="xl" aria-label="Alignment" onMouseDown={keepSelection} w={48}>
              <AlignIcon size={18} />
              <IconChevronDown size={12} />
            </ActionIcon>
          </Menu.Target>
          <Menu.Dropdown>
            {ALIGNS.map((a) => (
              <Menu.Item
                key={a.value}
                onMouseDown={keepSelection}
                leftSection={<a.icon size={16} />}
                rightSection={a.value === now.align ? <IconCheck size={14} /> : null}
                onClick={() => chain().setTextAlign(a.value).run()}
              >
                {a.label}
              </Menu.Item>
            ))}
          </Menu.Dropdown>
        </Menu>
        <Tool label="Numbered list" active={now.numbered} onClick={() => chain().toggleOrderedList().run()}>
          <IconListNumbers size={18} />
        </Tool>
        <Separator />
        <Menu withinPortal position="bottom-end" shadow="md">
          <Menu.Target>
            <ActionIcon variant="subtle" color="gray" size="lg" radius="xl" aria-label="More formatting options" onMouseDown={keepSelection}>
              <IconDotsVertical size={18} />
            </ActionIcon>
          </Menu.Target>
          <Menu.Dropdown>
            <Menu.Item onMouseDown={keepSelection} leftSection={<IconList size={16} />} rightSection={now.bullets ? <IconCheck size={14} /> : null} onClick={() => chain().toggleBulletList().run()}>
              Bulleted list
            </Menu.Item>
            <Menu.Item
              onMouseDown={keepSelection}
              leftSection={<IconClearFormatting size={16} />}
              onClick={() => chain().unsetAllMarks().clearNodes().unsetTextAlign().run()}
            >
              Remove formatting
            </Menu.Item>
          </Menu.Dropdown>
        </Menu>
      </Group>
      <EditorContent editor={editor} className="kh-richtext kh-richtext-editor" />
    </Stack>
  )
}

/** The description as it was written (cleaned again before it is shown). */
export function RichTextView({ html }: { html: string }) {
  const clean = useMemo(
    () => DOMPurify.sanitize(html, { ALLOWED_TAGS: ['p', 'br', 'strong', 'b', 'em', 'i', 'u', 's', 'ul', 'ol', 'li', 'span'], ALLOWED_ATTR: ['style'] }),
    [html],
  )
  return <div className="kh-richtext" dangerouslySetInnerHTML={{ __html: clean }} />
}
