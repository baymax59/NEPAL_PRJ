// Charts that can also be read as a table (the table is how values are read without hovering). Used by the administration
// overview and by the station dashboards.

import { SegmentedControl, Table } from '@mantine/core'
import { IconChartBar, IconTable } from '@tabler/icons-react'
import { useState, type ReactNode } from 'react'
import { Panel } from './ui'

export const CHART_SERIES = (name: string, label: string, color = 'var(--kh-chart-1)') => [{ name, label, color }]

/** A chart with a table view of the same numbers. `heads` names the columns of a table with more than a label and one number. */
export function ChartPanel({ title, rows, heads, children }: { title: string; rows: (string | number)[][]; heads?: string[]; children: ReactNode }) {
  const [view, setView] = useState('chart')
  return (
    <Panel
      title={title}
      actions={
        <SegmentedControl
          size="xs"
          value={view}
          onChange={setView}
          data={[
            { value: 'chart', label: <IconChartBar size={14} aria-label="Chart" /> },
            { value: 'table', label: <IconTable size={14} aria-label="Table" /> },
          ]}
        />
      }
    >
      {view === 'chart' ? (
        children
      ) : (
        <Table fz="xs">
          {heads && (
            <Table.Thead>
              <Table.Tr>
                {heads.map((h, i) => (
                  <Table.Th key={h} ta={i === 0 ? 'left' : 'right'}>
                    {h}
                  </Table.Th>
                ))}
              </Table.Tr>
            </Table.Thead>
          )}
          <Table.Tbody>
            {rows.map((row) => (
              <Table.Tr key={String(row[0])}>
                {row.map((cell, i) => (
                  <Table.Td key={i} ta={i === 0 ? 'left' : 'right'}>
                    {cell}
                  </Table.Td>
                ))}
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}
    </Panel>
  )
}
