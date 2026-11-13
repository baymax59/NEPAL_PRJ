// A person's picture: their profile photo when they have one, else their initials. The photo needs the login, so it is fetched with it
// (an <img src> could not send it) and kept for the session; `version` changes whenever the photo does, so a new one is fetched then.

import { Avatar, Text } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { fetchPhoto } from '../api/endpoints'

function initialsOf(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .map((word) => word[0])
    .join('')
    .slice(0, 2)
    .toUpperCase()
}

export function UserAvatar({ id, name, version, size = 22 }: { id?: string; name: string; version?: number | string | null; size?: number }) {
  const photo = useQuery({
    queryKey: ['photo', id, version],
    queryFn: async () => URL.createObjectURL(await fetchPhoto(id as string)),
    enabled: Boolean(id) && version !== null && version !== undefined,
    staleTime: Infinity,
    gcTime: 30 * 60_000,
    retry: false,
  })
  return (
    <Avatar size={size} radius={size} color="hawk" variant="light" src={photo.data ?? null} alt={name}>
      <Text span fz={Math.max(9, Math.round(size / 2.4))} fw={700}>
        {initialsOf(name)}
      </Text>
    </Avatar>
  )
}
