// Chat inside the case: the team group and a private conversation with each other member of the team. Messages are permanent: nothing here edits or
// deletes one. The page asks for news every few seconds. An archived case keeps its conversations, read-only.

import { Badge, Box, Button, Group, Paper, ScrollArea, Stack, Text, Textarea, ThemeIcon, UnstyledButton } from '@mantine/core'
import { IconSend, IconUsersGroup } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router'
import { useAuth } from '../../auth/useAuth'
import { UserAvatar } from '../../components/UserAvatar'
import { kh } from '../api'
import { toastError } from '../feedback'
import { formatWhen } from '../time'
import type { ChatMessage, ChatThread } from '../types'
import { EmptyState, Loaded, Panel } from '../ui'
import { useCase } from './context'

const MAX = 4000
const KEY = (caseId: string) => ['kh', 'case', caseId, 'chat']

function ThreadButton({ thread, active, onClick }: { thread: ChatThread; active: boolean; onClick: () => void }) {
  const { user } = useAuth()
  const last = thread.last
  // who wrote the latest message: "You", or in the team conversation the writer's name (a private one is with the other person anyway)
  const by = !last ? '' : last.sender.id === user?.id ? 'You: ' : thread.kind === 'group' ? `${last.sender.display_name}: ` : ''
  return (
    <UnstyledButton
      onClick={onClick}
      aria-label={`${thread.title}${thread.unread ? `, ${thread.unread} unread` : ''}`}
      aria-current={active ? 'true' : undefined}
      p="xs"
      style={{ borderRadius: 6, background: active ? 'var(--mantine-color-default-hover)' : undefined, width: '100%' }}
    >
      <Group gap="sm" wrap="nowrap" align="flex-start">
        {thread.peer ? (
          <UserAvatar id={thread.peer.id} name={thread.peer.display_name} version={thread.peer.photo} size={32} />
        ) : (
          <ThemeIcon size={32} radius="xl" variant="light" color="hawk">
            <IconUsersGroup size={18} />
          </ThemeIcon>
        )}
        <Box style={{ minWidth: 0, flex: 1 }}>
          <Group justify="space-between" wrap="nowrap" gap={4}>
            <Text size="sm" fw={600} truncate>
              {thread.title}
            </Text>
            {thread.unread > 0 && (
              <Badge size="sm" circle color="red" aria-label={`${thread.unread} unread`}>
                {thread.unread}
              </Badge>
            )}
          </Group>
          <Text size="xs" c="dimmed" truncate>
            {last ? `${by}${last.preview}` : thread.kind === 'group' ? 'Everyone on the team' : 'Private: only the two of you'}
          </Text>
        </Box>
      </Group>
    </UnstyledButton>
  )
}

function Bubble({ message, group }: { message: ChatMessage; group: boolean }) {
  return (
    <Group justify={message.mine ? 'flex-end' : 'flex-start'} align="flex-end" gap="xs" wrap="nowrap">
      {!message.mine && <UserAvatar id={message.sender.id} name={message.sender.display_name} version={message.sender.photo} size={26} />}
      <Paper
        withBorder
        p="xs"
        radius="md"
        maw="75%"
        bg={message.mine ? 'var(--mantine-color-hawk-light)' : undefined}
        style={{ borderColor: message.mine ? 'var(--mantine-color-hawk-light-color)' : undefined }}
      >
        {!message.mine && group && (
          <Text size="xs" fw={600} c="hawk.4">
            {message.sender.display_name}
          </Text>
        )}
        <Text size="sm" style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>
          {message.body}
        </Text>
        <Text size="xs" c="dimmed" ta="right" mt={2}>
          {formatWhen(message.at)}
        </Text>
      </Paper>
    </Group>
  )
}

function Conversation({ thread, canWrite }: { thread: ChatThread; canWrite: boolean }) {
  const detail = useCase()
  const client = useQueryClient()
  const [text, setText] = useState('')
  const bottom = useRef<HTMLDivElement>(null)
  const messages = useQuery({ queryKey: [...KEY(detail.id), 'messages', thread.key], queryFn: () => kh.chatMessages(detail.id, thread.key), refetchInterval: 4000 })
  const newest = messages.data?.messages.at(-1)?.id ?? 0
  const send = useMutation({
    mutationFn: () => kh.chatSend(detail.id, thread.kind === 'group' ? null : thread.key, text.trim()),
    onSuccess: () => {
      setText('')
      void client.invalidateQueries({ queryKey: KEY(detail.id) })
    },
    onError: (error) => toastError(error, 'The message was not sent'),
  })
  // Reading the conversation clears its unread count (and its notice); the newest message seen is remembered.
  useEffect(() => {
    if (newest > 0 && thread.unread > 0) {
      void kh.chatRead(detail.id, thread.key, newest).then(() => client.invalidateQueries({ queryKey: [...KEY(detail.id), 'threads'] }))
    }
  }, [newest, thread.unread, thread.key, detail.id, client])
  useEffect(() => {
    bottom.current?.scrollIntoView?.({ block: 'end' })
  }, [newest, thread.key])
  const tooLong = text.length > MAX
  return (
    <Stack gap="xs" h="100%">
      <Loaded query={messages}>
        {(view) =>
          view.messages.length === 0 ? (
            <EmptyState title="No messages yet">{thread.kind === 'group' ? 'Write to everyone on the team.' : `Write to ${thread.title}: only the two of you see it.`}</EmptyState>
          ) : (
            <ScrollArea h={420} type="auto" offsetScrollbars>
              <Stack gap="xs" pr="xs">
                {view.messages.map((m) => (
                  <Bubble key={m.id} message={m} group={thread.kind === 'group'} />
                ))}
                <div ref={bottom} />
              </Stack>
            </ScrollArea>
          )
        }
      </Loaded>
      {canWrite ? (
        <Group gap="xs" align="flex-end" wrap="nowrap">
          <Textarea
            style={{ flex: 1 }}
            aria-label="Message"
            placeholder={thread.kind === 'group' ? 'Write to the team…' : `Write to ${thread.title}…`}
            autosize
            minRows={1}
            maxRows={5}
            value={text}
            error={tooLong ? `At most ${MAX} characters` : undefined}
            onChange={(e) => setText(e.currentTarget.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault()
                if (text.trim() && !tooLong && !send.isPending) send.mutate()
              }
            }}
          />
          <Button leftSection={<IconSend size={16} />} disabled={!text.trim() || tooLong} loading={send.isPending} onClick={() => send.mutate()}>
            Send
          </Button>
        </Group>
      ) : (
        <Text size="sm" c="dimmed">
          This case is archived: its conversations are kept, and no new messages can be written.
        </Text>
      )}
      <Text size="xs" c="dimmed">
        Messages are permanent: they cannot be edited or deleted, and each one shows who wrote it.
        {thread.kind === 'group' ? ' Everyone on the case team sees this conversation.' : ' Only you and ' + thread.title + ' see this conversation.'}
      </Text>
    </Stack>
  )
}

export function ChatTab() {
  const detail = useCase()
  const [search, setSearch] = useSearchParams()
  const threads = useQuery({ queryKey: [...KEY(detail.id), 'threads'], queryFn: () => kh.chatThreads(detail.id), refetchInterval: 5000, enabled: detail.can.chat })
  const wanted = search.get('with') ?? 'group'
  if (!detail.can.chat) {
    return (
      <EmptyState title="Chat is for the case's team">
        Only people on this case's team can write to each other here. Ask the Investigator who leads the case to add you to the team.
      </EmptyState>
    )
  }
  return (
    <Loaded query={threads}>
      {(list) => {
        const active = list.find((t) => t.key === wanted) ?? list[0]
        return (
          <Group align="flex-start" gap="md" wrap="wrap">
            <Box w={{ base: '100%', sm: 300 }} style={{ flexShrink: 0 }}>
              <Panel title="Conversations" p="xs">
                <Stack gap={2}>
                  {list.map((t) => (
                    <ThreadButton key={t.key} thread={t} active={t.key === active.key} onClick={() => setSearch(t.key === 'group' ? {} : { with: t.key }, { replace: true })} />
                  ))}
                </Stack>
              </Panel>
            </Box>
            <Box style={{ flex: 1, minWidth: 280 }}>
              <Panel title={active.title}>
                <Conversation key={active.key} thread={active} canWrite={detail.can.write_chat} />
              </Panel>
            </Box>
          </Group>
        )
      }}
    </Loaded>
  )
}
