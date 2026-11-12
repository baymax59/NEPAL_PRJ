import {
  Alert,
  Badge,
  Button,
  Center,
  Group,
  Loader,
  Stack,
  Tabs,
  Text,
  Title,
} from '@mantine/core'
import {
  IconAlertCircle,
  IconArrowLeft,
  IconChartBar,
  IconDeviceMobile,
  IconEye,
  IconFileImport,
  IconGitMerge,
  IconMap,
  IconSearch,
  IconShieldCheck,
  IconTimeline,
  IconUsers,
} from '@tabler/icons-react'
import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router'
import { getCdrSession } from '../api/endpoints'
import { ErrorAlert } from '../components/common'

// 15 canonical CDR tabs. Auth flows through the httpOnly cdr_session cookie;
// no credentials appear in any iframe src URL.
const CDR_TABS = [
  { key: 'import', label: 'Import & Evidence', icon: <IconFileImport size={16} />, view: 'upload' },
  { key: 'search', label: 'Search & Analytics', icon: <IconSearch size={16} />, view: 'search' },
  { key: 'graph', label: 'Call Graph', icon: <IconGitMerge size={16} />, view: 'graph' },
  { key: 'frequency', label: 'Frequency & Behaviour', icon: <IconChartBar size={16} />, view: 'frequency' },
  { key: 'top-contacts', label: 'Top Contacts', icon: <IconUsers size={16} />, view: 'top-contacts' },
  { key: 'common-contacts', label: 'Common Contacts', icon: <IconUsers size={16} />, view: 'common-contacts' },
  { key: 'devices', label: 'Devices & SIMs', icon: <IconDeviceMobile size={16} />, view: 'devices' },
  { key: 'map', label: 'Map & Location', icon: <IconMap size={16} />, view: 'map' },
  { key: 'timeline', label: 'Timeline', icon: <IconTimeline size={16} />, view: 'timeline' },
  { key: 'common-towers', label: 'Common Towers', icon: <IconMap size={16} />, view: 'common-towers' },
  { key: 'co-location', label: 'Co-location', icon: <IconMap size={16} />, view: 'co-location' },
  { key: 'anomalies', label: 'Anomalies', icon: <IconAlertCircle size={16} />, view: 'anomalies' },
  { key: 'audit', label: 'Audit Trail', icon: <IconShieldCheck size={16} />, view: 'audit' },
  { key: 'custody', label: 'Chain of Custody', icon: <IconShieldCheck size={16} />, view: 'custody' },
  { key: 'reports', label: 'Reports', icon: <IconEye size={16} />, view: 'reports' },
] as const

function CdrModuleFrame({ src, title }: { src: string; title: string }) {
  return (
    <iframe
      src={src}
      title={title}
      style={{
        width: '100%',
        height: 'calc(100vh - 220px)',
        border: 'none',
        borderRadius: 8,
        background: '#f7f9f8',
      }}
      sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
      allow=""
      referrerPolicy="same-origin"
    />
  )
}

function CdrModulePlaceholder({ label }: { label: string }) {
  return (
    <Alert color="gray" variant="light" icon={<IconAlertCircle size={18} />}>
      <Text size="sm" fw={500}>
        {label} — CDR service not configured
      </Text>
      <Text size="xs" c="dimmed" mt={4}>
        Set CDR_D1_API_URL / CDR_D2_API_URL / CDR_D3_API_URL in your environment and restart the
        backend. The CDR Analysis services must be running.
      </Text>
    </Alert>
  )
}

function CdrShell({ displayId }: { displayId: string }) {
  const session = useQuery({
    queryKey: ['cdr-session', displayId],
    queryFn: () => getCdrSession(displayId),
  })

  if (session.isPending) {
    return (
      <Center py="xl">
        <Loader />
      </Center>
    )
  }
  if (session.error) return <ErrorAlert error={session.error} />

  const { case_id, display_name, role } = session.data

  // Auth is carried by the httpOnly cdr_session cookie set by /api/cdr/session.
  // The browser sends it automatically on same-origin requests inside each iframe.
  // No credentials appear in src URLs or localStorage.
  const d1Src = `/cdr/d1/`
  const d2Src = (view: string) => `/cdr/d2/${view}?case_id=${encodeURIComponent(case_id)}`
  const d3Src = (view: string) => `/cdr/d3/cases/${encodeURIComponent(case_id)}/${view}`

  function iframeFor(key: string) {
    switch (key) {
      case 'import':
        return <CdrModuleFrame src={d1Src} title="Import & Evidence" />
      case 'search':
        return <CdrModuleFrame src={d2Src('search')} title="Search & Analytics" />
      case 'graph':
        return <CdrModuleFrame src={d2Src('graph')} title="Call Graph" />
      case 'frequency':
        return <CdrModuleFrame src={d2Src('frequency')} title="Frequency & Behaviour" />
      case 'top-contacts':
        return <CdrModuleFrame src={d2Src('top-contacts')} title="Top Contacts" />
      case 'common-contacts':
        return <CdrModuleFrame src={d2Src('common-contacts')} title="Common Contacts" />
      case 'devices':
        return <CdrModuleFrame src={d2Src('devices')} title="Devices & SIMs" />
      case 'map':
        return <CdrModuleFrame src={d3Src('map')} title="Map & Location" />
      case 'timeline':
        return <CdrModuleFrame src={d3Src('timeline')} title="Timeline" />
      case 'common-towers':
        return <CdrModuleFrame src={d3Src('common-towers')} title="Common Towers" />
      case 'co-location':
        return <CdrModuleFrame src={d3Src('co-location')} title="Co-location" />
      case 'anomalies':
        return <CdrModuleFrame src={d3Src('anomalies')} title="Anomalies" />
      case 'audit':
        return <CdrModuleFrame src={d3Src('audit')} title="Audit Trail" />
      case 'custody':
        return <CdrModuleFrame src={d3Src('custody')} title="Chain of Custody" />
      case 'reports':
        return <CdrModuleFrame src={d3Src('reports')} title="Reports" />
      default:
        return <CdrModulePlaceholder label="Unknown view" />
    }
  }

  return (
    <Stack gap="md">
      <Group justify="space-between">
        <Button
          component={Link}
          to={`/cases/${displayId}`}
          variant="subtle"
          size="xs"
          leftSection={<IconArrowLeft size={14} />}
        >
          Back to case
        </Button>
        <Group gap="xs">
          <Text size="xs" c="dimmed">
            Signed in as {display_name}
          </Text>
          <Badge variant="light" color="gray" size="sm">
            {role}
          </Badge>
        </Group>
      </Group>

      <div>
        <Title order={2} size="h4">
          CDR Analysis
        </Title>
        <Group gap="xs" mt={4}>
          <Badge variant="outline" color="gray" radius="sm" size="sm">
            Case {case_id}
          </Badge>
          <Text size="xs" c="dimmed">
            All analysis is scoped to this case. No other case's data is accessible.
          </Text>
        </Group>
      </div>

      {/* DEV-ONLY notice: remove when a real identity provider is wired up */}
      <Alert color="yellow" variant="light" icon={<IconAlertCircle size={16} />}>
        <Text size="xs" fw={500}>
          DEV-ONLY authentication — no real identity provider is connected.
        </Text>
        <Text size="xs" c="dimmed" mt={2}>
          Base map source unavailable — no approved provider is configured. The map view uses a
          synthetic placeholder that is not real geography and is not court evidence.
        </Text>
      </Alert>

      <Tabs defaultValue="import" keepMounted={false}>
        <Tabs.List style={{ flexWrap: 'wrap' }}>
          {CDR_TABS.map((tab) => (
            <Tabs.Tab key={tab.key} value={tab.key} leftSection={tab.icon}>
              {tab.label}
            </Tabs.Tab>
          ))}
        </Tabs.List>

        {CDR_TABS.map((tab) => (
          <Tabs.Panel key={tab.key} value={tab.key} pt="md">
            {iframeFor(tab.key)}
          </Tabs.Panel>
        ))}
      </Tabs>

      <Text size="xs" c="dimmed">
        Note: CDR records are observations from call detail records and are not proof of identity
        or wrongdoing. All results carry supporting record IDs. Reports generated here are not
        certified forensic reports without a proper chain of custody procedure.
      </Text>
    </Stack>
  )
}

export function CdrAnalysisPage() {
  const { displayId = '' } = useParams()
  if (!displayId) return <ErrorAlert error={new Error('No case selected')} />
  return <CdrShell displayId={displayId} />
}
