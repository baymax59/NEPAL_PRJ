import { Button, Stack, Text, Title } from '@mantine/core'
import { Link } from 'react-router'

export function NotFoundPage() {
  return (
    <Stack align="flex-start">
      <Title order={1} size="h3">
        Page not found
      </Title>
      <Text c="dimmed">There is nothing at this address.</Text>
      <Button component={Link} to="/" variant="light">
        Go to search
      </Button>
    </Stack>
  )
}
