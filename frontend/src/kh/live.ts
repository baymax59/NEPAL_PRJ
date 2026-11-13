// Live notices and live pages: follows the Server-Sent Events stream /api/v1/notifications/stream.
// The browser's EventSource can't send the login header, so the stream is read with fetch. The stream never carries
// case content:
// - `notices`: counts; when they change, the notices and the lists they concern are fetched again.
// - `activity` (CM-8): a fingerprint of what the open page shows (the page is told to the server as `watch`, worked out
//   from the address). When it changes because a colleague added a note, uploaded..., the page's data is
//   fetched again: the page stays current without reloading. Only the queries on screen are fetched again, and only
//   after a real change (every read is audited, so nothing is re-read "just in case").

import { notifications } from '@mantine/notifications'
import { useQueryClient, type QueryKey } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { tokenStore } from '../api/client'

export type LiveStatus = 'connecting' | 'live' | 'offline'

/** Lists that notices are about: refreshed when a notice arrives. */
const AFFECTED = [['kh', 'notifications'], ['kh', 'my-cases'], ['kh', 'case']]

const ID = '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
const PAGES: [RegExp, string][] = [
  [new RegExp(`^/kh/case/(${ID})(?:/|$)`, 'i'), 'case'],
  [new RegExp(`^/kh/evidence/(${ID})(?:/|$)`, 'i'), 'evidence'],
]

/** What the page at this address shows, as the stream's `watch` (null: nothing to follow beyond notices). */
export function watchFor(pathname: string): string | null {
  for (const [pattern, kind] of PAGES) {
    const match = pattern.exec(pathname)
    if (match) return `${kind}:${match[1].toLowerCase()}`
  }
  return pathname === '/kh/admin' || pathname.startsWith('/kh/admin/') ? 'admin' : null
}

/** The data a watched page shows: fetched again (if on screen) when the stream says it changed. */
export function keysFor(watch: string): QueryKey[] {
  if (watch === 'admin') return [['kh', 'admin'], ['kh', 'cases']]
  return [['kh', 'case'], ['kh', 'evidence'], ['kh', 'artifact']]
}

export function parseEvent(block: string): { event: string; data: string } {
  let event = 'message'
  const data: string[] = []
  for (const line of block.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) data.push(line.slice(5).trim())
  }
  return { event, data: data.join('\n') }
}

/** A value that settles: navigating from one page to the next changes `watch` twice in a moment; connect once. */
function useSettled<T>(value: T, ms: number): T {
  const [settled, setSettled] = useState(value)
  useEffect(() => {
    const timer = window.setTimeout(() => setSettled(value), ms)
    return () => window.clearTimeout(timer)
  }, [value, ms])
  return settled
}

export function useLiveNotices(enabled: boolean, watch: string | null = null): { unread: number | null; status: LiveStatus } {
  const queryClient = useQueryClient()
  const [unread, setUnread] = useState<number | null>(null)
  const [status, setStatus] = useState<LiveStatus>('connecting')
  // Kept across reconnections: a new connection's first counts don't refresh anything unless they differ.
  const seen = useRef<{ unread: number; latest: number | null } | undefined>(undefined)
  const page = useSettled(watch, 300)

  useEffect(() => {
    if (!enabled || typeof window.fetch !== 'function') return
    // One connection's state, changed in place (the stream callbacks below outlive a render).
    const link = {
      stopped: false, controller: null as AbortController | null, timer: undefined as number | undefined, delay: 2000,
      // The page's last fingerprint: the first one is the baseline. Kept when the stream reconnects (every 10 minutes,
      // or after a network error), so a change made in between still refreshes the page.
      marker: undefined as string | undefined,
    }

    const handle = (block: string) => {
      const { event, data } = parseEvent(block)
      if (event === 'notices') {
        const state = JSON.parse(data) as { unread: number; latest: number | null }
        const previous = seen.current
        seen.current = state
        setUnread(state.unread)
        if (previous === undefined || (previous.unread === state.unread && previous.latest === state.latest)) return
        for (const key of AFFECTED) queryClient.invalidateQueries({ queryKey: key })
        if (state.latest !== null && (previous.latest === null || state.latest > previous.latest)) {
          notifications.show({ color: 'hawk', title: 'New notice', message: 'Open the bell at the top to read it.', autoClose: 5000 })
        }
      } else if (event === 'activity' && page !== null) {
        const { marker } = JSON.parse(data) as { marker: string }
        const before = link.marker
        link.marker = marker
        // The page loaded its data just before connecting: only a later change means something new to show.
        if (before !== undefined && before !== marker) {
          for (const key of keysFor(page)) queryClient.invalidateQueries({ queryKey: key })
        }
      } else if (event === 'expired') {
        link.stopped = true
        setStatus('offline')
      }
    }

    const connect = async () => {
      const token = tokenStore.get()
      if (!token || link.stopped) return
      link.controller = new AbortController()
      try {
        const url = page ? `/api/v1/notifications/stream?watch=${encodeURIComponent(page)}` : '/api/v1/notifications/stream'
        const response = await fetch(url, {
          headers: { Authorization: `Bearer ${token}`, Accept: 'text/event-stream' },
          signal: link.controller.signal,
          cache: 'no-store',
        })
        if (response.status === 401) {
          setStatus('offline') // logged out: the next ordinary request takes the user to the login page
          return
        }
        if (!response.ok || !response.body) throw new Error(`stream answered ${response.status}`)
        setStatus('live')
        link.delay = 2000
        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        for (;;) {
          const { value, done } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true }).replaceAll('\r\n', '\n')
          for (let end = buffer.indexOf('\n\n'); end >= 0; end = buffer.indexOf('\n\n')) {
            handle(buffer.slice(0, end))
            buffer = buffer.slice(end + 2)
          }
        }
      } catch {
        if (link.stopped) return
      }
      if (!link.stopped) {
        setStatus('connecting')
        link.timer = window.setTimeout(connect, link.delay)
        link.delay = Math.min(link.delay * 2, 30000)
      }
    }

    void connect()
    return () => {
      link.stopped = true
      link.controller?.abort()
      window.clearTimeout(link.timer)
    }
  }, [enabled, queryClient, page])

  return { unread, status }
}
