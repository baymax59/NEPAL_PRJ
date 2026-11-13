// My profile: the official details (from the officer register, read-only) and what the person fills in about themselves: email, phone and
// job title. Only the person themselves can change it.

import { Alert, Button, FileButton, Group, Stack, Text, TextInput } from '@mantine/core'
import { IconInfoCircle } from '@tabler/icons-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { getProfile, removePhoto, saveProfile, uploadPhoto } from '../../api/endpoints'
import type { Profile } from '../../api/types'
import { useAuth } from '../../auth/useAuth'
import { UserAvatar } from '../../components/UserAvatar'
import { kh } from '../api'
import { toastDone, toastError } from '../feedback'
import { humanize, roleLabel } from '../labels'
import { formatWhen } from '../time'
import { EmptyState, Facts, Loaded, PageHeader, Panel } from '../ui'
import { MyCaseTable } from './CasesPage'

const PHOTO_TYPES = ['image/jpeg', 'image/png', 'image/webp']
const PHOTO_MAX_BYTES = 2 * 1024 * 1024

/** The photo: choose a JPEG, PNG or WebP picture (up to 2 MB); the server makes it a small square. Only the person can change their own. */
function PhotoPanel({ profile }: { profile: Profile }) {
  const client = useQueryClient()
  const { reload } = useAuth()
  const [problem, setProblem] = useState<string | null>(null)
  const done = async (saved: Profile, message: string) => {
    client.setQueryData(['profile'], saved)
    await reload() // the top bar shows the new picture
    toastDone(message)
  }
  const upload = useMutation({
    mutationFn: (file: File) => uploadPhoto(file),
    onSuccess: (saved) => done(saved, 'Your photo is saved'),
    onError: (error) => toastError(error, 'Your photo was not saved'),
  })
  const remove = useMutation({
    mutationFn: removePhoto,
    onSuccess: (saved) => done(saved, 'Your photo is removed'),
    onError: (error) => toastError(error, 'Your photo was not removed'),
  })
  const choose = (file: File | null) => {
    if (!file) return
    if (!PHOTO_TYPES.includes(file.type)) return setProblem('Use a JPEG, PNG or WebP picture')
    if (file.size > PHOTO_MAX_BYTES) return setProblem('The picture is larger than 2 MB: choose a smaller one')
    setProblem(null)
    upload.mutate(file)
  }
  return (
    <Group gap="lg" wrap="nowrap" align="center">
      <UserAvatar id={profile.id ?? undefined} name={profile.display_name} version={profile.photo_updated_at ?? null} size={96} />
      <Stack gap={6}>
        <Group gap="xs">
          <FileButton onChange={choose} accept={PHOTO_TYPES.join(',')}>
            {(props) => (
              <Button {...props} loading={upload.isPending} size="sm">
                {profile.photo_updated_at ? 'Change photo' : 'Upload a photo'}
              </Button>
            )}
          </FileButton>
          {profile.photo_updated_at && (
            <Button variant="default" size="sm" loading={remove.isPending} onClick={() => remove.mutate()}>
              Remove photo
            </Button>
          )}
        </Group>
        {problem ? (
          <Text size="xs" c="red">
            {problem}
          </Text>
        ) : (
          <Text size="xs" c="dimmed">
            JPEG, PNG or WebP, up to 2 MB. It is cut to a square and made small; other people in your organisation see it next to your name.
          </Text>
        )}
      </Stack>
    </Group>
  )
}

const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/
const PHONE = /^[0-9+()\-. ]{6,40}$/

function ProfileForm({ profile }: { profile: Profile }) {
  const client = useQueryClient()
  const { reload } = useAuth()
  const [email, setEmail] = useState(profile.email ?? '')
  const [phone, setPhone] = useState(profile.phone ?? '')
  const [jobTitle, setJobTitle] = useState(profile.job_title ?? '')
  const emailBad = email.trim() !== '' && !EMAIL.test(email.trim())
  const phoneBad = phone.trim() !== '' && !PHONE.test(phone.trim())
  const unchanged = email.trim() === (profile.email ?? '') && phone.trim() === (profile.phone ?? '') && jobTitle.trim() === (profile.job_title ?? '')
  const mutation = useMutation({
    mutationFn: () => saveProfile({ email: email.trim() || null, phone: phone.trim() || null, job_title: jobTitle.trim() || null }),
    onSuccess: async (saved) => {
      client.setQueryData(['profile'], saved)
      await reload() // the prompt to fill in the profile goes away
      toastDone('Your profile is saved')
    },
    onError: (error) => toastError(error, 'Your profile was not saved'),
  })
  return (
    <Stack gap="sm">
      <TextInput label="Email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.currentTarget.value)} maxLength={200} error={emailBad ? 'Not a valid email address' : undefined} />
      <TextInput
        label="Phone"
        type="tel"
        autoComplete="tel"
        value={phone}
        onChange={(e) => setPhone(e.currentTarget.value)}
        maxLength={40}
        error={phoneBad ? 'Use digits, spaces and + ( ) - . only (6 to 40 characters)' : undefined}
      />
      <TextInput label="Job title" description="For example: Investigating officer, cyber cell" value={jobTitle} onChange={(e) => setJobTitle(e.currentTarget.value)} maxLength={100} />
      <Group justify="space-between">
        <Text size="xs" c="dimmed">
          {profile.profile_updated_at ? `Last saved ${formatWhen(profile.profile_updated_at)}` : 'Not filled in yet'}
        </Text>
        <Button disabled={emailBad || phoneBad || (unchanged && profile.profile_updated_at !== null)} loading={mutation.isPending} onClick={() => mutation.mutate()}>
          Save my profile
        </Button>
      </Group>
    </Stack>
  )
}

export function MyProfilePage() {
  const query = useQuery({ queryKey: ['profile'], queryFn: getProfile })
  const teams = useQuery({ queryKey: ['kh', 'my-cases'], queryFn: () => kh.myCases() })
  return (
    <Stack gap="md" maw={980}>
      <PageHeader eyebrow="Account" title="My profile" />
      <Loaded query={query}>
        {(profile) => (
          <>
            {profile.profile_updated_at === null && (
              <Alert color="hawk" variant="light" icon={<IconInfoCircle size={18} />}>
                Fill in your email and phone, so your Supervisor can reach you.
              </Alert>
            )}
            <Panel title="Your photo">
              <PhotoPanel profile={profile} />
            </Panel>
            <Panel title="About you">
              <ProfileForm profile={profile} />
            </Panel>
            <Panel title={`Teams I am on${teams.data ? ` (${teams.data.length})` : ''}`} p="0">
              <Loaded query={teams}>
                {(list) =>
                  list.length === 0 ? (
                    <EmptyState title="Not on any team yet">When an Investigator adds you to a case, or you lead one, its team appears here with your part in it.</EmptyState>
                  ) : (
                    <MyCaseTable items={list} />
                  )
                }
              </Loaded>
            </Panel>
            <Panel title="Official details">
              <Stack gap="xs">
                <Facts
                  cols={2}
                  items={[
                    ['Name', profile.display_name],
                    ['Username', `@${profile.username}`],
                    ['Officer ID', profile.officer_number ?? 'not in the register'],
                    ['Rank', profile.rank ?? 'not in the register'],
                    ['Station', profile.stations.length ? profile.stations.join(', ') : 'all stations'],
                    ['Role', roleLabel(profile.org_role)],
                    ['Clearance', humanize(profile.clearance)],
                  ]}
                />
                <Text size="xs" c="dimmed">
                  These come from the officer register and your Supervisor or Administrator. To change them, ask them.
                </Text>
              </Stack>
            </Panel>
          </>
        )}
      </Loaded>
    </Stack>
  )
}
