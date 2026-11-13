// Comments on the case, an exhibit, a note or a task. Editing adds a new comment that replaces yours; the
// earlier wording stays visible ("edited"), because nothing is overwritten.

import { Button, Collapse, Group, Paper, Stack, Text, Textarea } from '@mantine/core'
import { IconMessage } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useAuth } from '../auth/useAuth'
import { kh } from './api'
import type { CommentOut } from './types'
import { Loaded, PersonName, When } from './ui'
import { toastError, useOnceKey } from './feedback'

type Target = 'case' | 'evidence' | 'artifact' | 'task'

export function Comments({ caseId, targetType, targetId, canWrite = true }: { caseId: string; targetType: Target; targetId: string; canWrite?: boolean }) {
  const queryClient = useQueryClient()
  const { user } = useAuth()
  const [key, renew] = useOnceKey()
  const [body, setBody] = useState('')
  const [editing, setEditing] = useState<CommentOut | null>(null)
  const queryKey = ['kh', 'case', caseId, 'comments', targetType, targetId]
  const query = useQuery({ queryKey, queryFn: () => kh.comments(caseId, targetType, targetId) })
  const add = useMutation({
    mutationFn: () => kh.addComment(caseId, { target_type: targetType, target_id: targetId, body: body.trim(), replaces_comment_id: editing?.id ?? null }, key),
    onSuccess: () => {
      renew()
      setBody('')
      setEditing(null)
      queryClient.invalidateQueries({ queryKey })
    },
    onError: (error) => toastError(error, 'Comment not added'),
  })
  return (
    <Stack gap="xs">
      <Loaded query={query}>
        {(comments) => {
          const current = comments.filter((c) => c.current)
          return current.length === 0 ? (
            <Text size="sm" c="dimmed">
              No comments yet.
            </Text>
          ) : (
            current.map((comment) => <CommentItem key={comment.id} comment={comment} all={comments} mine={comment.author?.id === user?.id} onEdit={() => {
              setEditing(comment)
              setBody(comment.body)
            }} canWrite={canWrite} />)
          )
        }}
      </Loaded>
      {canWrite && (
        <Stack gap={6}>
          <Textarea
            placeholder={editing ? 'Edit your comment (the earlier wording is kept)' : 'Add a comment'}
            value={body}
            onChange={(e) => setBody(e.currentTarget.value)}
            autosize
            minRows={2}
            maxLength={5000}
            aria-label="Comment"
          />
          <Group justify="flex-end" gap="xs">
            {editing && (
              <Button size="xs" variant="default" onClick={() => {
                setEditing(null)
                setBody('')
              }}>
                Cancel edit
              </Button>
            )}
            <Button size="xs" leftSection={<IconMessage size={14} />} disabled={!body.trim()} loading={add.isPending} onClick={() => add.mutate()}>
              {editing ? 'Save edit' : 'Comment'}
            </Button>
          </Group>
        </Stack>
      )}
    </Stack>
  )
}

function CommentItem({ comment, all, mine, onEdit, canWrite }: { comment: CommentOut; all: CommentOut[]; mine: boolean; onEdit: () => void; canWrite: boolean }) {
  const [showEarlier, setShowEarlier] = useState(false)
  const earlier: CommentOut[] = []
  for (let id = comment.replaces_comment_id; id; ) {
    const previous = all.find((c) => c.id === id)
    if (!previous) break
    earlier.push(previous)
    id = previous.replaces_comment_id
  }
  return (
    <Paper withBorder p="xs" radius="sm">
      <Group justify="space-between" gap="xs" mb={4}>
        <Group gap="xs">
          <PersonName person={comment.author} size="xs" />
          <When at={comment.created_at} size="xs" />
          {earlier.length > 0 && (
            <Button variant="subtle" size="compact-xs" color="gray" onClick={() => setShowEarlier((s) => !s)}>
              edited · {showEarlier ? 'hide' : 'show'} earlier wording
            </Button>
          )}
        </Group>
        {mine && canWrite && (
          <Button variant="subtle" size="compact-xs" onClick={onEdit}>
            Edit
          </Button>
        )}
      </Group>
      <Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>
        {comment.body}
      </Text>
      <Collapse expanded={showEarlier}>
        <Stack gap={4} mt="xs">
          {earlier.map((c) => (
            <Text key={c.id} size="xs" c="dimmed" style={{ whiteSpace: 'pre-wrap', borderLeft: '2px solid var(--mantine-color-default-border)', paddingLeft: 8 }}>
              <When at={c.created_at} size="xs" />: {c.body}
            </Text>
          ))}
        </Stack>
      </Collapse>
    </Paper>
  )
}
