// Case assistant helpers. The conversation is kept in the page only; it is not saved anywhere.

import type { ChatAnswer, ChatTurn } from '../api/types'

export interface Exchange {
  question: string
  compareWith: string | null
  answer: ChatAnswer
}

/** The previous question and answer, so a follow-up question ("and why?") makes sense. */
export function historyFor(exchanges: Exchange[]): ChatTurn[] {
  return exchanges
    .flatMap((e): ChatTurn[] => [
      { role: 'user', content: e.question },
      { role: 'assistant', content: e.answer.answer.slice(0, 4000) },
    ])
    .slice(-2)
}
