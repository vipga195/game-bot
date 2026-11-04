import { useCallback, useEffect, useState, type FormEvent, type ReactElement } from 'react'
import { api, type NotifyChannel } from './api'

type NotifyLevel = 'error' | 'all'
type NotifyKind = 'telegram' | 'teams' | 'zalo' | 'facebook'
const KIND_LABEL: Record<NotifyKind, string> = { telegram: 'Telegram', teams: 'Teams', zalo: 'Zalo', facebook: 'Facebook' }

export function NotifyPanel(): ReactElement {
  const [channels, setChannels] = useState<NotifyChannel[]>([])
  const [kind, setKind] = useState<NotifyKind>('telegram')
  const [name, setName] = useState('')
  const [secret, setSecret] = useState('')
  const [chatId, setChatId] = useState('')
  const [pageId, setPageId] = useState('')
  const [recipientId, setRecipientId] = useState('')
  const [level, setLevel] = useState<NotifyLevel>('error')
  const [msg, setMsg] = useState('')
  const [msgOk, setMsgOk] = useState(false)
  const [sendImage, setSendImage] = useState(false)
  const [results, setResults] = useState<Record<string, 'ok' | 'fail'>>({})

  const reload = useCallback(async (): Promise<void> => {
    try {
      setChannels(await api.notifyChannels())
    } catch {
      setMsg('Không tải được danh sách kênh')
    }
  }, [])

  useEffect(() => {
    api.notifyChannels().then(setChannels).catch(() => setMsg('Không tải được danh sách kênh'))
  }, [])

  const handleTest = async (id: string): Promise<void> => {
    try {
      const result = await api.testNotify(id)
      setResults((prev) => ({ ...prev, [id]: result.ok ? 'ok' : 'fail' }))
    } catch {
      setResults((prev) => ({ ...prev, [id]: 'fail' }))
    }
  }

  const handleDelete = async (id: string): Promise<void> => {
    if (!window.confirm('Xoá kênh này?')) return
    try {
      await api.deleteNotifyChannel(id)
      setResults((prev) => {
        const { [id]: _removed, ...rest } = prev
        return rest
      })
      await reload()
    } catch {
      setMsgOk(false)
      setMsg('Xoá kênh thất bại')
    }
  }

  const handleSubmit = async (e: FormEvent<HTMLFormElement>): Promise<void> => {
    e.preventDefault()
    try {
      let config: NotifyChannel['config'] = {}
      if (kind === 'telegram') {
        config = { chat_id: chatId, send_image: sendImage }
      } else if (kind === 'zalo') {
        config = { chat_id: chatId }
      } else if (kind === 'teams') {
        config = {}
      } else if (kind === 'facebook') {
        config = { page_id: pageId, recipient_id: recipientId }
      }
      await api.addNotifyChannel({ kind, name, level, config, secret })
      setSecret('')
      setName('')
      setSendImage(false)
      setMsgOk(true)
      setMsg('Đã thêm kênh')
      await reload()
    } catch {
      setMsgOk(false)
      setMsg('Thêm kênh thất bại')
    }
  }

  return (
    <>
      <form onSubmit={handleSubmit}>
        <h3>Thêm kênh {KIND_LABEL[kind]}</h3>
        <select aria-label="Loại kênh" value={kind} onChange={(e) => { setKind(e.target.value as NotifyKind); setSecret(''); setChatId(''); setPageId(''); setRecipientId(''); setSendImage(false) }}>
          <option value="telegram">Telegram</option>
          <option value="teams">Teams</option>
          <option value="zalo">Zalo</option>
          <option value="facebook">Facebook</option>
        </select>
        <input
          aria-label="Tên kênh"
          placeholder="Tên kênh"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
        <select
          aria-label="Mức báo"
          value={level}
          onChange={(e) => setLevel(e.target.value === 'all' ? 'all' : 'error')}
        >
          <option value="error">Chỉ lỗi</option>
          <option value="all">Lỗi và cảnh báo</option>
        </select>
        {kind === 'telegram' || kind === 'zalo' ? (
          <>
            <input
              aria-label="Bot token"
              type="password"
              autoComplete="off"
              placeholder="Bot token"
              value={secret}
              onChange={(e) => setSecret(e.target.value)}
              required
            />
            <input
              aria-label="Chat id"
              placeholder="Chat id"
              value={chatId}
              onChange={(e) => setChatId(e.target.value)}
              required
            />
            {kind === 'telegram' && (
              <>
                <label>
                  <input type="checkbox" aria-label="Gửi kèm ảnh chụp màn hình lỗi" checked={sendImage} onChange={(e) => setSendImage(e.target.checked)} />
                  Gửi kèm ảnh chụp màn hình lỗi
                </label>
                <p className="hint">Ảnh có thể chứa thông tin nhạy cảm (mật khẩu, mã OTP) và được gửi tới Telegram</p>
              </>
            )}
          </>
        ) : kind === 'teams' ? (
          <input
            aria-label="Webhook URL"
            type="password"
            autoComplete="off"
            placeholder="Webhook URL"
            value={secret}
            onChange={(e) => setSecret(e.target.value)}
            required
          />
        ) : kind === 'facebook' ? (
          <>
            <input
              aria-label="Page access token"
              type="password"
              autoComplete="off"
              placeholder="Page access token"
              value={secret}
              onChange={(e) => setSecret(e.target.value)}
              required
            />
            <input
              aria-label="Page id"
              placeholder="Page id"
              value={pageId}
              onChange={(e) => setPageId(e.target.value)}
              required
            />
            <input
              aria-label="Recipient id (PSID)"
              placeholder="Recipient id (PSID)"
              value={recipientId}
              onChange={(e) => setRecipientId(e.target.value)}
              required
            />
            <p className="hint">Facebook chỉ gửi được trong 24 giờ sau khi người nhận nhắn tin cho Page.</p>
          </>
        ) : null}
        <button type="submit">Thêm kênh</button>
      </form>
      {msg && <p role="status" className={msgOk ? 'ok' : 'err'}>{msg}</p>}
      {channels.length === 0 && <p className="empty">Chưa có kênh nào. Thêm kênh Telegram để nhận báo lỗi.</p>}
      {channels.map((channel) => (
        <div key={channel.id}>
          <span>{channel.name}</span>
          <span>{channel.kind}</span>
          <span>{channel.level === 'error' ? 'Chỉ lỗi' : 'Lỗi và cảnh báo'}</span>
          <span>{channel.config.chat_id ?? channel.config.page_id ?? ''}</span>
          <span>{channel.config.recipient_id ?? ''}</span>
          <button onClick={() => handleTest(channel.id)}>Gửi thử</button>
          <span>{results[channel.id] === 'ok' ? 'Đã gửi' : results[channel.id] === 'fail' ? 'Gửi thất bại' : ''}</span>
          <button onClick={() => handleDelete(channel.id)}>Xoá</button>
        </div>
      ))}
    </>
  )
}
