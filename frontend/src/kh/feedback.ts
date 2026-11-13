// Messages after an action, and the Idempotency-Key of a form.

import { notifications } from '@mantine/notifications'
import { useState } from 'react'
import { ApiError } from '../api/client'
import { newKey } from './api'

export function errorText(error: unknown): string {
  return error instanceof ApiError || error instanceof Error ? error.message : 'Something went wrong.'
}

export const toastError = (error: unknown, title = 'Not done') =>
  notifications.show({ color: 'red', title, message: errorText(error), autoClose: 8000 })
export const toastDone = (message: string) => notifications.show({ color: 'teal', message, autoClose: 4000 })

/** An Idempotency-Key for one form: the same while the form is open, renewed after a success. */
export function useOnceKey(): [string, () => void] {
  const [key, setKey] = useState(newKey)
  return [key, () => setKey(newKey())]
}
