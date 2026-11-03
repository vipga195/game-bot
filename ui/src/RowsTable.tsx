import { useCallback, useEffect, useState } from 'react'
import { newRow } from './newRow'
import { api, type Account, type AgentEvent, type Game, type Instance, type Row } from './api'

const MODE_LABEL: Record<string, string> = { event: 'Hoạt động', task: 'Nhiệm vụ', train: 'Train' }

export function RowsTable({ onTeach }: { onTeach: (row: Row) => void }) {
  const [rows, setRows] = useState<Row[]>([])
  const [instances, setInstances] = useState<Instance[]>([])
  const [games, setGames] = useState<Game[]>([])
  const [accounts, setAccounts] = useState<Account[]>([])
  const [live, setLive] = useState<Record<number, AgentEvent>>({})
  const [paused, setPaused] = useState<Record<number, boolean>>({})
  const [error, setError] = useState('')

  const reload = useCallback(async () => {
    try {
      const [r, g, a] = await Promise.all([api.rows(), api.games(), api.accounts()])
      setRows(r); setGames(g); setAccounts(a); setError('')
    } catch (e) { setError(String(e)) }
  }, [])
  const scan = async () => { try { setInstances(await api.instances()) } catch (e) { setError(String(e)) } }

  useEffect(() => { reload(); scan(); return api.events((e) => setLive((l) => ({ ...l, [e.row]: e }))) }, [reload])

  const save = async (row: Row) => { await api.saveRow(row); await reload() }
  const patch = (row: Row, p: Partial<Row>) => save({ ...row, ...p })
  const move = (row: Row, i: number, d: number) => {
    const order = [...row.mode_priority]
    const j = i + d
    if (j < 0 || j >= order.length) return
    ;[order[i], order[j]] = [order[j], order[i]]
    patch(row, { mode_priority: order })
  }
  const pickInstance = (row: Row, key: string) => {
    const [kind, ref] = key.split('|')
    patch(row, { emulator_kind: kind ?? '', emulator_ref: ref ?? '' })
  }

  return (
    <section>
      <div className="bar">
        <button onClick={() => save(newRow())}>Thêm dòng</button>
        <button onClick={scan}>Quét máy</button>
        {error && <span className="err">{error}</span>}
      </div>
      <table>
        <thead>
          <tr><th>Tên</th><th>Máy giả lập</th><th>Game</th><th>Tài khoản</th><th>Ưu tiên</th><th>Lịch</th><th>Trạng thái</th><th /></tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const ev = live[row.id!]
            const state = ev?.state ?? row.state ?? 'idle'
            return (
              <tr key={row.id}>
                <td><input aria-label="Tên" defaultValue={row.name} onBlur={(e) => e.target.value !== row.name && patch(row, { name: e.target.value })} /></td>
                <td>
                  <select aria-label="Máy giả lập" value={`${row.emulator_kind}|${row.emulator_ref}`} onChange={(e) => pickInstance(row, e.target.value)}>
                    <option value="|">-- chọn --</option>
                    {instances.map((i) => <option key={`${i.kind}|${i.ref}`} value={`${i.kind}|${i.ref}`}>{i.kind}: {i.name}{i.running ? ' (chạy)' : ''}</option>)}
                  </select>
                </td>
                <td>
                  <select aria-label="Game" value={row.game_id} onChange={(e) => patch(row, { game_id: e.target.value })}>
                    <option value="">-- chọn --</option>
                    {games.map((g) => <option key={g.id} value={g.id}>{g.id}</option>)}
                  </select>
                </td>
                <td>
                  <select aria-label="Tài khoản" value={row.account_id} onChange={(e) => patch(row, { account_id: e.target.value })}>
                    <option value="">-- chọn --</option>
                    {accounts.filter((a) => !row.game_id || a.game_id === row.game_id).map((a) => <option key={a.id} value={a.id}>{a.label}</option>)}
                  </select>
                </td>
                <td>
                  {row.mode_priority.map((m, i) => (
                    <div key={m} className="prio">
                      {i + 1}. {MODE_LABEL[m] ?? m}
                      <button aria-label={`Lên ${m}`} onClick={() => move(row, i, -1)}>↑</button>
                      <button aria-label={`Xuống ${m}`} onClick={() => move(row, i, 1)}>↓</button>
                    </div>
                  ))}
                </td>
                <td className="sched">
                  <label>Giờ chạy <input aria-label="Từ" type="time" value={row.schedule.active_from} onChange={(e) => patch(row, { schedule: { ...row.schedule, active_from: e.target.value } })} />
                    – <input aria-label="Đến" type="time" value={row.schedule.active_to} onChange={(e) => patch(row, { schedule: { ...row.schedule, active_to: e.target.value } })} /></label>
                  <label>Nhiệm vụ mỗi <input aria-label="Chu kỳ nhiệm vụ (phút)" type="number" min={1} value={row.schedule.interval_min.task ?? 120} onChange={(e) => patch(row, { schedule: { ...row.schedule, interval_min: { ...row.schedule.interval_min, task: Number(e.target.value) } } })} /> phút</label>
                </td>
                <td><span className={`state ${state}`}>{state}</span>{ev?.error && <div className="err">{ev.error}</div>}{ev?.message && <div>{ev.message}</div>}</td>
                <td>
                  <button onClick={() => api.runRow(row.id!, row.mode_priority[0] === 'event' ? 'task' : row.mode_priority[0])}>Chạy</button>
                  <button onClick={async () => { const p = !paused[row.id!]; await api.pauseRow(row.id!, p); setPaused({ ...paused, [row.id!]: p }) }}>{paused[row.id!] ? 'Tiếp tục' : 'Pause'}</button>
                  <button onClick={() => onTeach(row)}>Dạy lại</button>
                  <button onClick={async () => { await api.deleteRow(row.id!); reload() }}>Xoá</button>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <AddGameAccount games={games} onDone={reload} />
    </section>
  )
}

function AddGameAccount({ games, onDone }: { games: Game[]; onDone: () => void }) {
  const [g, setG] = useState({ id: '', package: '' })
  const [a, setA] = useState({ game_id: '', label: '', username: '', password: '' })
  return (
    <div className="forms">
      <form onSubmit={async (e) => { e.preventDefault(); await api.saveGame(g); setG({ id: '', package: '' }); onDone() }}>
        <h3>Thêm game</h3>
        <input aria-label="Mã game" placeholder="Mã game" value={g.id} onChange={(e) => setG({ ...g, id: e.target.value })} required />
        <input aria-label="Package" placeholder="com.example.game" value={g.package} onChange={(e) => setG({ ...g, package: e.target.value })} required />
        <button>Lưu game</button>
      </form>
      <form onSubmit={async (e) => { e.preventDefault(); await api.addAccount(a); setA({ ...a, label: '', username: '', password: '' }); onDone() }}>
        <h3>Thêm tài khoản</h3>
        <select aria-label="Game của tài khoản" value={a.game_id} onChange={(e) => setA({ ...a, game_id: e.target.value })} required>
          <option value="">-- game --</option>
          {games.map((x) => <option key={x.id} value={x.id}>{x.id}</option>)}
        </select>
        <input aria-label="Nhãn" placeholder="Nhãn" value={a.label} onChange={(e) => setA({ ...a, label: e.target.value })} required />
        <input aria-label="Tên đăng nhập" placeholder="Tên đăng nhập" value={a.username} onChange={(e) => setA({ ...a, username: e.target.value })} required />
        <input aria-label="Mật khẩu" type="password" autoComplete="off" placeholder="Mật khẩu (lưu trong keyring)" value={a.password} onChange={(e) => setA({ ...a, password: e.target.value })} required />
        <button>Lưu tài khoản</button>
      </form>
    </div>
  )
}
