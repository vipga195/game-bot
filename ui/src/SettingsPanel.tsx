import { AddGameAccount } from './AddGameAccount'
import { NotifyPanel } from './NotifyPanel'
import { SyncPanel } from './SyncPanel'

export function SettingsPanel() {
  return (
    <section>
      <h2>Cài đặt</h2>
      <details open>
        <summary>Game &amp; tài khoản</summary>
        <AddGameAccount />
      </details>
      <details>
        <summary>Thông báo lỗi</summary>
        <NotifyPanel />
      </details>
      <details>
        <summary>Đồng bộ server (nâng cao)</summary>
        <SyncPanel />
      </details>
    </section>
  )
}
