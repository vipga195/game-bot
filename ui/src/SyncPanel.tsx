import { useState } from 'react'
import { api } from './api'

export function SyncPanel() {
  const [url, setUrl] = useState('http://127.0.0.1:8100')
  const [token, setToken] = useState('')
  const [passphrase, setPassphrase] = useState('')
  const [out, setOut] = useState('')
  return (
    <section>
      <form onSubmit={async (e) => {
        e.preventDefault()
        try {
          const r = await api.sync({ url, token, passphrase: passphrase || undefined })
          setOut(`Đẩy ${r.pushed}, nhận ${r.applied}, ảnh mẫu mới ${r.assets}, xung đột ${r.conflicts.length}`)
        } catch (err) { setOut(String(err)) }
      }}>
        <input aria-label="URL server" value={url} onChange={(e) => setUrl(e.target.value)} />
        <input aria-label="Token" type="password" value={token} onChange={(e) => setToken(e.target.value)} />
        <input aria-label="Passphrase" type="password" placeholder="Passphrase (để trống = không đồng bộ mật khẩu)" value={passphrase} onChange={(e) => setPassphrase(e.target.value)} />
        <button>Đồng bộ ngay</button>
      </form>
      {out && <p role="status">{out}</p>}
    </section>
  )
}
