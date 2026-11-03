import { useCallback, useEffect, useState } from 'react'
import { api, type Game } from './api'

export function AddGameAccount() {
  const [games, setGames] = useState<Game[]>([])
  const [g, setG] = useState({ id: '', package: '' })
  const [a, setA] = useState({ game_id: '', label: '', username: '', password: '' })
  const [msg, setMsg] = useState('')
  const reload = useCallback(async () => {
    try { setGames(await api.games()) } catch (e) { setMsg(String(e)) }
  }, [])
  useEffect(() => { reload() }, [reload])
  const done = (text: string) => { setMsg(text); reload() }
  return (
    <>
      <div className="forms">
        <form onSubmit={async (e) => { e.preventDefault(); await api.saveGame(g); setG({ id: '', package: '' }); done('Đã lưu game') }}>
          <h3>Thêm game</h3>
          <input aria-label="Mã game" placeholder="Mã game" value={g.id} onChange={(e) => setG({ ...g, id: e.target.value })} required />
          <input aria-label="Package" placeholder="com.example.game" value={g.package} onChange={(e) => setG({ ...g, package: e.target.value })} required />
          <button>Lưu game</button>
        </form>
        <form onSubmit={async (e) => { e.preventDefault(); await api.addAccount(a); setA({ ...a, label: '', username: '', password: '' }); done('Đã lưu tài khoản') }}>
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
      {msg && <p role="status">{msg}</p>}
    </>
  )
}
