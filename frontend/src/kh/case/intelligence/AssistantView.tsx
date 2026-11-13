// The case assistant: answers only from what you may see in the case as it stands now, citing exhibit or note, version
// and page. The conversation stays in this page only.

import { Accordion, Alert, Badge, Button, Group, Loader, Paper, Stack, Text, Textarea, Tooltip } from '@mantine/core'
import { IconInfoCircle, IconMessageChatbot, IconSend, IconTrash } from '@tabler/icons-react'
import { useMutation } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { kh } from '../../api'
import { errorText } from '../../feedback'
import type { AnswerSource, CaseAnswer, CaseDetail } from '../../types'
import { Notices, SourceLink } from './common'
import { pageText } from './format'

const EXAMPLES = [
  'What happened on the day of the first transfer?',
  'Which phone numbers and accounts appear in the evidence?',
  'What does the complaint say about how the fraud began?',
]

interface Exchange {
  question: string
  answer: CaseAnswer
}

function sourceLabel(s: AnswerSource): string {
  if (s.kind === 'case_record') return `Recorded facts of ${s.display_id}`
  const pages = pageText(s.page_start, s.page_end)
  return `${s.display_id} v${s.version_number}${pages ? `, ${pages}` : ''} · ${s.title}`
}

/** The answer with [S2] shown as a marker naming its source. Text only, never HTML. */
function AnswerText({ answer }: { answer: CaseAnswer }) {
  const byId = new Map(answer.sources.map((s) => [s.id, s]))
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

function Sources({ caseId, exchange }: { caseId: string; exchange: Exchange }) {
  const { sources } = exchange.answer
  return (
    <Accordion variant="contained" chevronPosition="left">
      <Accordion.Item value="sources">
        <Accordion.Control>
          <Text size="sm">
            Sources given to the assistant ({sources.length}, {sources.filter((s) => s.cited).length} cited)
          </Text>
        </Accordion.Control>
        <Accordion.Panel>
          <Stack gap="xs">
            {sources.map((s) => (
              <Paper key={s.id} withBorder p="xs" radius="sm">
                <Group gap="xs" mb={4} wrap="wrap">
                  <Badge size="sm" variant="light">
                    {s.id}
                  </Badge>
                  {s.kind === 'case_record' ? (
                    <Text size="sm" fw={500}>
                      Recorded facts of {s.display_id}
                    </Text>
                  ) : (
                    <>
                      <SourceLink caseId={caseId} source={s} pages={pageText(s.page_start, s.page_end)} />
                      <Text size="sm">{s.title}</Text>
                    </>
                  )}
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

export function AssistantView({ detail }: { detail: CaseDetail }) {
  const [question, setQuestion] = useState('')
  const [exchanges, setExchanges] = useState<Exchange[]>([])
  const history = exchanges
    .flatMap((e) => [
      { role: 'user' as const, content: e.question },
      { role: 'assistant' as const, content: e.answer.answer.slice(0, 4000) },
    ])
    .slice(-2)
  const ask = useMutation({
    mutationFn: (text: string) => kh.askCase(detail.id, { question: text, history }),
    onSuccess: (answer, text) => {
      setExchanges((previous) => [...previous, { question: text, answer }])
      setQuestion('')
    },
  })
  function submit(event: FormEvent) {
    event.preventDefault()
    if (question.trim() && !ask.isPending) ask.mutate(question.trim())
  }
  return (
    <Stack gap="md">
      <Alert color="blue" variant="light" icon={<IconInfoCircle size={18} />}>
        <Text size="sm">
          Ask about this investigation as it stands now. Answers use only what you may see and cite it as [S1], [S2]… with the exhibit or
          note, its version and the page. If the records don't say, the assistant tells you so. It runs on this computer, so an answer can take a
          few minutes. It can make mistakes, and it never decides guilt or what action to take.
        </Text>
      </Alert>
      {exchanges.map((exchange, i) => (
        <Stack key={i} gap="xs">
          <Paper bg="var(--mantine-color-default-hover)" p="sm" radius="md">
            <Text size="xs" c="dimmed">
              You asked
            </Text>
            <Text size="sm">{exchange.question}</Text>
          </Paper>
          <Paper withBorder p="sm" radius="md">
            <Group gap="xs" mb={6}>
              <IconMessageChatbot size={16} aria-hidden />
              <Text size="xs" c="dimmed">
                Case assistant
              </Text>
              {!exchange.answer.answered && (
                <Badge size="xs" color="gray" variant="light">
                  Not in the records
                </Badge>
              )}
            </Group>
            <AnswerText answer={exchange.answer} />
          </Paper>
          <Notices notices={exchange.answer.notices} />
          <Sources caseId={detail.id} exchange={exchange} />
          <Text size="xs" c="dimmed">
            {exchange.answer.model} · {exchange.answer.seconds} s · {exchange.answer.disclaimer}
          </Text>
        </Stack>
      ))}
      {ask.isPending && (
        <Paper withBorder p="sm" radius="md">
          <Group gap="sm" wrap="nowrap">
            <Loader size="sm" />
            <Text size="sm">Reading the case and writing an answer. On this computer this usually takes 2–3 minutes.</Text>
          </Group>
        </Paper>
      )}
      {ask.error && (
        <Alert color="red" variant="light" title="No answer">
          {errorText(ask.error)}
        </Alert>
      )}
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
          <Textarea label="Your question" value={question} onChange={(e) => setQuestion(e.currentTarget.value)} autosize minRows={2} maxLength={1000} disabled={ask.isPending} />
          <Group justify="space-between">
            <Button variant="subtle" color="gray" leftSection={<IconTrash size={16} />} onClick={() => setExchanges([])} disabled={!exchanges.length || ask.isPending}>
              Clear conversation
            </Button>
            <Button type="submit" leftSection={<IconSend size={16} />} loading={ask.isPending} disabled={!question.trim()}>
              Ask
            </Button>
          </Group>
        </Stack>
      </form>
    </Stack>
  )
}
