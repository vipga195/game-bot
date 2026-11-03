import { useState } from 'react'
import type { Row } from './api'
import { RecorderPanel } from './RecorderPanel'
import { RowsTable } from './RowsTable'
import { SettingsPanel } from './SettingsPanel'
import './index.css'

type Tab = 'rows' | 'recorder' | 'settings'

export default function App() {
  const [tab, setTab] = useState<Tab>('rows')
  const [teachRow, setTeachRow] = useState<Row | null>(null)
  return (
    <main>
      <h1>Game Bot</h1>
      <nav>
        <button aria-pressed={tab === 'rows'} onClick={() => setTab('rows')}>Bot</button>
        <button aria-pressed={tab === 'recorder'} onClick={() => setTab('recorder')}>Ghi macro</button>
        <button aria-pressed={tab === 'settings'} onClick={() => setTab('settings')}>Cài đặt</button>
      </nav>
      {tab === 'rows' && <RowsTable onTeach={(r) => { setTeachRow(r); setTab('recorder') }} />}
      {tab === 'recorder' && <RecorderPanel row={teachRow} />}
      {tab === 'settings' && <SettingsPanel />}
    </main>
  )
}
