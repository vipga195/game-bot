import { Fragment, useCallback, useEffect, useState } from 'react'
import { newRow } from './newRow'
import { api, type Account, type AgentEvent, type Game, type Instance, type Row } from './api'

const STATE_LABEL: Record<string, string> = { idle: 'Nghỉ', running: 'Đang chạy', queued: 'Đang chờ', error: 'Lỗi' }
const MODE_LABEL: Record<string, string> = { event: 'Hoạt động', task: 'Nhiệm vụ', train: 'Train' }

export function RowsTable({ onTeach }: { onTeach: (row: Row) => void }) {
  const [rows, setRows] = useState<Row[]>([])
  const [instances, setInstances] = useState<Instance[]>([])
  const [games, setGames] = useState<Game[]>([])
  const [accounts, setAccounts] = useState<Account[]>([])
  const [live, setLive] = useState<Record<number, AgentEvent>>({})
  const [paused, setPaused] = useState<Record<number, boolean>>({})
  const [error, setError] = useState('')
  const [loaded, setLoaded] = useState(false)

  const reload = useCallback(async () => {
    try {
      const [r, g, a] = await Promise.all([api.rows(), api.games(), api.accounts()])
      setRows(r); setGames(g); setAccounts(a); setError(''); setLoaded(true)
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
        <button className="primary" onClick={() => save(newRow())}>+ Thêm dòng</button>
        <button onClick={scan}>Quét máy giả lập</button>
        {error && <span className="err">{error}</span>}
      </div>
      {loaded && rows.length === 0 && (
        <p className="empty">
          Chưa có dòng nào. Bấm <b>+ Thêm dòng</b>, chọn máy giả lập, game và tài khoản, rồi bấm <b>Chạy</b>.
          Chưa có game/tài khoản? Thêm ở tab <b>Cài đặt</b>.
        </p>
      )}
      {rows.length > 0 && (
      <table>
        <thead>
          <tr><th>Tên</th><th>Máy giả lập</th><th>Game</th><th>Tài khoản</th><th>Trạng thái</th><th /></tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const ev = live[row.id!]
            const state = ev?.state ?? row.state ?? 'idle'
            return (
              <Fragment key={row.id}>
              <tr>
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
                <td><span className={`state ${state}`}>{STATE_LABEL[state] ?? state}</span>{ev?.error && <div className="err">{ev.error}</div>}{ev?.message && <div>{ev.message}</div>}</td>
                <td className="actions">
                  <button className="primary" onClick={() => api.runRow(row.id!, row.mode_priority[0] === 'event' ? 'task' : row.mode_priority[0])}>Chạy</button>
                  <button onClick={async () => { const p = !paused[row.id!]; await api.pauseRow(row.id!, p); setPaused({ ...paused, [row.id!]: p }) }}>{paused[row.id!] ? 'Tiếp tục' : 'Tạm dừng'}</button>
                  <details className="menu">
                    <summary aria-label="Thêm hành động">⋯</summary>
                    <div className="menu-list">
                      <button onClick={() => onTeach(row)}>Ghi lại macro</button>
                      <button onClick={async () => { await api.deleteRow(row.id!); reload() }}>Xoá dòng</button>
                    </div>
                  </details>
                </td>
              </tr>
              <tr className="more">
                <td colSpan={6}>
                  <details>
                    <summary>Ưu tiên &amp; lịch chạy</summary>
                    <div className="more-body">
                      <div>
                        {row.mode_priority.map((m, i) => (
                          <div key={m} className="prio">
                            {i + 1}. {MODE_LABEL[m] ?? m}
                            <button aria-label={`Lên ${m}`} onClick={() => move(row, i, -1)}>↑</button>
                            <button aria-label={`Xuống ${m}`} onClick={() => move(row, i, 1)}>↓</button>
                          </div>
                        ))}
                      </div>
                      <div className="sched">
                        <label>Giờ chạy <input aria-label="Từ" type="time" value={row.schedule.active_from} onChange={(e) => patch(row, { schedule: { ...row.schedule, active_from: e.target.value } })} />
                          – <input aria-label="Đến" type="time" value={row.schedule.active_to} onChange={(e) => patch(row, { schedule: { ...row.schedule, active_to: e.target.value } })} /></label>
                        <label>Nhiệm vụ mỗi <input aria-label="Chu kỳ nhiệm vụ (phút)" type="number" min={1} value={row.schedule.interval_min.task ?? 120} onChange={(e) => patch(row, { schedule: { ...row.schedule, interval_min: { ...row.schedule.interval_min, task: Number(e.target.value) } } })} /> phút</label>
                      </div>
                    </div>
                  </details>
                </td>
              </tr>
              </Fragment>
            )
          })}
        </tbody>
      </table>
      )}
    </section>
  )
}
