import { useRef, useState } from 'react'
import { api, type Instance, type Row } from './api'

export function RecorderPanel({ row }: { row: Row | null }) {
  const [instances, setInstances] = useState<Instance[]>([])
  const [serial, setSerial] = useState('')
  const [mode, setMode] = useState('task')
  const [screenName, setScreenName] = useState('')
  const [fromScreen, setFromScreen] = useState('')
  const [toScreen, setToScreen] = useState('')
  const [src, setSrc] = useState('')
  const [msg, setMsg] = useState('')
  const img = useRef<HTMLImageElement>(null)
  const gameId = row?.game_id ?? ''

  const refresh = () => setSrc(api.recorderScreenUrl())
  const run = async (f: () => Promise<unknown>, ok: string) => {
    try { await f(); setMsg(ok) } catch (e) { setMsg(String(e)) }
  }
  const onClick = (e: React.MouseEvent<HTMLImageElement>) => {
    const el = img.current!
    const r = el.getBoundingClientRect()
    const x = Math.round(((e.clientX - r.left) / r.width) * el.naturalWidth)
    const y = Math.round(((e.clientY - r.top) / r.height) * el.naturalHeight)
    run(async () => {
      await api.recorderTap({ x, y, from_screen: fromScreen || undefined, to_screen: toScreen || undefined })
      refresh()
    }, `Đã ghi bước tại (${x}, ${y})`)
  }

  return (
    <section>
      <h2>Recorder {row ? `— ${row.name} / ${gameId || 'chưa chọn game'}` : ''}</h2>
      <div className="bar">
        <button onClick={async () => setInstances(await api.instances())}>Quét máy</button>
        <select aria-label="Máy ghi" value={serial} onChange={(e) => setSerial(e.target.value)}>
          <option value="">-- máy đang chạy --</option>
          {instances.filter((i) => i.serial).map((i) => <option key={i.serial!} value={i.serial!}>{i.name} ({i.serial})</option>)}
        </select>
        <select aria-label="Chế độ" value={mode} onChange={(e) => setMode(e.target.value)}>
          {['login', 'task', 'train', 'event'].map((m) => <option key={m}>{m}</option>)}
        </select>
        <button disabled={!serial || !gameId} onClick={() => run(async () => { await api.recorderStart({ serial, game_id: gameId, mode }); refresh() }, 'Đã bắt đầu ghi')}>Bắt đầu ghi</button>
        <button onClick={refresh}>Làm mới màn hình</button>
        <button onClick={() => run(async () => { const r = await api.recorderFinish(); setMsg(`Đã lưu ${r.script_id}: ${r.steps} bước`) }, '')}>Kết thúc & lưu</button>
      </div>
      <div className="bar">
        <input aria-label="Tên màn hình" placeholder="Tên màn hình (vd. login)" value={screenName} onChange={(e) => setScreenName(e.target.value)} />
        <button disabled={!screenName} onClick={() => run(() => api.recorderMark({ name: screenName, region: [0.1, 0.03, 0.9, 0.15] }), `Đã đánh dấu màn hình ${screenName}`)}>Đánh dấu màn hình hiện tại</button>
        <input aria-label="Màn hình trước" placeholder="từ màn hình" value={fromScreen} onChange={(e) => setFromScreen(e.target.value)} />
        <input aria-label="Màn hình sau" placeholder="tới màn hình" value={toScreen} onChange={(e) => setToScreen(e.target.value)} />
      </div>
      {msg && <p role="status">{msg}</p>}
      {src && <img ref={img} src={src} alt="Màn hình giả lập" className="screen" onClick={onClick} />}
    </section>
  )
}
