// The case assistant (chatbot): questions about one case, answered only from its records, with sources.
// The conversation lives in this component only: it is not saved anywhere and is gone when you leave the page.

import { Accordion, Alert, Badge, Button, Drawer, Group, Loader, Paper, Stack, Text, Textarea, TextInput, Tooltip } from '@mantine/core'
import { IconInfoCircle, IconMessageChatbot, IconSend, IconTrash } from '@tabler/icons-react'
import { useMutation } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { askAboutCase } from '../api/endpoints'
import type { ChatAnswer, ChatSource } from '../api/types'
import { historyFor, type Exchange } from '../lib/chat'
import { pageLabel } from '../lib/format'
import { ErrorAlert, Notices } from './common'

const EXAMPLES = [
  'Why did the court decide the way it did?',
  'Which provisions were applied, and on which pages?',
  'What happened before the case reached this court?',
]

function sourceLabel(source: ChatSource): string {
  if (source.kind === 'record') return `Recorded facts of ${source.case_display_id}`
  return `${source.case_display_id}, judgment ${pageLabel(source.page_start, source.page_end)}`
}

/** The answer text, with [S2] shown as a marker that names the source. Text is rendered as text, never HTML. */
function AnswerText({ answer, sources }: { answer: ChatAnswer; sources: ChatSource[] }) {
  const byId = new Map(sources.map((s) => [s.id, s]))
  return (
    <Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>
      {answer.answer.split(/(\[S\d+\])/).map((part, i) => {
        const source = byId.get(part.slice(1, -1))
        if (!source) return part
        return (
          <Tooltip key={i} label={sourceLabel(source)}>
            <Badge component="span" size="xs" variant="light" mx={2} style={{ cursor: 'help', verticalAlign: 'baseline' }}>
              {source.id}
            </Badge>
          </Tooltip>
        )
      })}
    </Text>
  )
}

function SourceList({ sources }: { sources: ChatSource[] }) {
  const cited = sources.filter((s) => s.cited).length
  return (
    <Accordion variant="contained" chevronPosition="left">
      <Accordion.Item value="sources">
        <Accordion.Control>
          <Text size="sm">
            Sources given to the assistant ({sources.length}, {cited} cited)
          </Text>
        </Accordion.Control>
        <Accordion.Panel>
          <Stack gap="xs">
            {sources.map((s) => (
              <Paper key={s.id} withBorder p="xs" radius="sm">
                <Group gap="xs" mb={4}>
                  <Badge size="sm" variant="light">
                    {s.id}
                  </Badge>
                  <Text size="sm" fw={500}>
                    {sourceLabel(s)}
                  </Text>
                  {s.cited && (
                    <Badge size="xs" color="teal" variant="light">
                      Cited in the answer
                    </Badge>
                  )}
                </Group>
                <Text size="xs" c="dimmed">
                  {s.excerpt}
                </Text>
              </Paper>
            ))}
          </Stack>
        </Accordion.Panel>
      </Accordion.Item>
    </Accordion>
  )
}

export function ExchangeView({ exchange }: { exchange: Exchange }) {
  const { answer } = exchange
  return (
    <Stack gap="xs">
      <Paper bg="var(--mantine-color-gray-light)" p="sm" radius="md">
        <Text size="xs" c="dimmed">
          You asked{exchange.compareWith ? ` (compared with ${exchange.compareWith})` : ''}
        </Text>
        <Text size="sm">{exchange.question}</Text>
      </Paper>
      <Paper withBorder p="sm" radius="md">
        <Group gap="xs" mb={6}>
          <IconMessageChatbot size={16} aria-hidden />
          <Text size="xs" c="dimmed">
            Case assistant
          </Text>
          {!answer.answered && (
            <Badge size="xs" color="gray" variant="light">
              Not in the records
            </Badge>
          )}
        </Group>
        <AnswerText answer={answer} sources={answer.sources} />
      </Paper>
      <Notices notices={answer.notices} />
      <SourceList sources={answer.sources} />
      <Text size="xs" c="dimmed">
        {answer.model} · {answer.seconds} s · {answer.disclaimer}
      </Text>
    </Stack>
  )
}

export function CaseAssistant({ displayId, opened, onClose }: { displayId: string; opened: boolean; onClose: () => void }) {
  const [question, setQuestion] = useState('')
  const [compareWith, setCompareWith] = useState('')
  const [exchanges, setExchanges] = useState<Exchange[]>([])
  const ask = useMutation({
    mutationFn: (vars: { question: string; compareWith: string | null }) =>
      askAboutCase(displayId, vars.question, historyFor(exchanges), vars.compareWith ?? undefined),
    onSuccess: (answer, vars) => {
      setExchanges((previous) => [...previous, { ...vars, answer }])
      setQuestion('')
    },
  })

  function submit(event: FormEvent) {
    event.preventDefault()
    const text = question.trim()
    if (text && !ask.isPending) ask.mutate({ question: text, compareWith: compareWith.trim() || null })
  }

  return (
    <Drawer
      opened={opened}
      onClose={onClose}
      position="right"
      size="xl"
      title={
        <Group gap="xs">
          <IconMessageChatbot size={20} aria-hidden />
          <Text fw={600}>Case assistant</Text>
          <Badge variant="outline" color="gray" radius="sm">
            {displayId}
          </Badge>
        </Group>
      }
    >
      <Stack gap="md">
        <Alert color="blue" variant="light" icon={<IconInfoCircle size={18} />}>
          <Text size="sm">
            Ask about this case. Answers use only this case's records and cite them as [S1], [S2]…; the sources are
            listed under each answer. If the records don't say, the assistant tells you so. It runs on this computer,
            so an answer usually takes 2–4 minutes. It can make mistakes, and it does not decide guilt, liability or what
            action to take.
          </Text>
        </Alert>

        {exchanges.map((exchange, i) => (
          <ExchangeView key={i} exchange={exchange} />
        ))}

        {ask.isPending && (
          <Paper withBorder p="sm" radius="md">
            <Group gap="sm" wrap="nowrap">
              <Loader size="sm" />
              <Text size="sm">
                Reading the case records and writing an answer. This usually takes 2–4 minutes. You can close this panel; the
                answer will be here when you reopen it.
              </Text>
            </Group>
          </Paper>
        )}
        {ask.error && <ErrorAlert error={ask.error} title="No answer" />}

        <form onSubmit={submit}>
          <Stack gap="sm">
            {exchanges.length === 0 && (
              <Group gap="xs">
                {EXAMPLES.map((example) => (
                  <Button key={example} size="compact-xs" variant="light" onClick={() => setQuestion(example)}>
                    {example}
                  </Button>
                ))}
              </Group>
            )}
            <Textarea
              label="Your question"
              value={question}
              onChange={(e) => setQuestion(e.currentTarget.value)}
              autosize
              minRows={2}
              maxLength={1000}
              disabled={ask.isPending}
            />
            <TextInput
              label="Compare with another case (optional)"
              description="Enter a case ID. Its records are added as sources; you must be allowed to see that case."
              placeholder="e.g. SC-ESCR010000092023"
              value={compareWith}
              onChange={(e) => setCompareWith(e.currentTarget.value)}
              maxLength={64}
              disabled={ask.isPending}
            />
            <Group justify="space-between">
              <Button
                variant="subtle"
                color="gray"
                leftSection={<IconTrash size={16} />}
                onClick={() => setExchanges([])}
                disabled={exchanges.length === 0 || ask.isPending}
              >
                Clear conversation
              </Button>
              <Button type="submit" leftSection={<IconSend size={16} />} loading={ask.isPending} disabled={!question.trim()}>
                Ask
              </Button>
            </Group>
          </Stack>
        </form>
      </Stack>
    </Drawer>
  )
}
