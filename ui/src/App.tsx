import { useState } from 'react'
import type { Row } from './api'
import { RecorderPanel } from './RecorderPanel'
import { RowsTable } from './RowsTable'
import { SyncPanel } from './SyncPanel'
import './index.css'

type Tab = 'rows' | 'recorder' | 'sync'

export default function App() {
  const [tab, setTab] = useState<Tab>('rows')
  const [teachRow, setTeachRow] = useState<Row | null>(null)
  return (
    <main>
      <h1>Game Bot</h1>
      <nav>
        <button aria-pressed={tab === 'rows'} onClick={() => setTab('rows')}>Quản lý</button>
        <button aria-pressed={tab === 'recorder'} onClick={() => setTab('recorder')}>Recorder</button>
        <button aria-pressed={tab === 'sync'} onClick={() => setTab('sync')}>Đồng bộ</button>
      </nav>
      {tab === 'rows' && <RowsTable onTeach={(r) => { setTeachRow(r); setTab('recorder') }} />}
      {tab === 'recorder' && <RecorderPanel row={teachRow} />}
      {tab === 'sync' && <SyncPanel />}
    </main>
  )
}
