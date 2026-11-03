export const BASE = import.meta.env.VITE_AGENT_URL ?? 'http://127.0.0.1:8731'

export interface Instance { kind: string; name: string; ref: string; serial: string | null; running: boolean }
export interface Schedule {
  active_from: string
  active_to: string
  utc_offset_min: number
  interval_min: Record<string, number>
  event_at: Record<string, string>
  event_window_min: number
  event_lead_min: number
  last_run: Record<string, string>
}
export interface Row {
  id?: number
  name: string
  emulator_kind: string
  emulator_ref: string
  game_id: string
  account_id: string
  mode_priority: string[]
  schedule: Schedule
  enabled: boolean
  state?: string
}
export interface Game { id: string; package: string }
export interface Account { id: string; game_id: string; label: string; username: string }
export interface AgentEvent { row: number; state: string; mode?: string; error?: string; message?: string }

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(BASE + path, {
    ...init,
    headers: init?.body ? { 'Content-Type': 'application/json' } : undefined,
  })
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`)
  return r.json() as Promise<T>
}
const post = <T,>(path: string, body?: unknown) =>
  req<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) })

export const api = {
  instances: () => req<Instance[]>('/instances'),
  rows: () => req<Row[]>('/rows'),
  saveRow: (row: Row) => post<Row>('/rows', row),
  deleteRow: (id: number) => req(`/rows/${id}`, { method: 'DELETE' }),
  runRow: (id: number, mode: string) => post<{ ok: boolean; error: string | null }>(`/rows/${id}/run?mode=${mode}`),
  pauseRow: (id: number, paused: boolean) => post(`/rows/${id}/pause?paused=${paused}`),
  games: () => req<Game[]>('/games'),
  saveGame: (g: Game) => post<Game>('/games', g),
  accounts: () => req<Account[]>('/accounts'),
  addAccount: (a: { game_id: string; label: string; username: string; password: string }) =>
    post<Account>('/accounts', a),
  recorderStart: (b: { serial: string; game_id: string; mode: string }) =>
    post<{ script_id: string }>('/recorder/start', b),
  recorderScreenUrl: () => `${BASE}/recorder/screen?t=${Date.now()}`,
  recorderTap: (b: { x: number; y: number; from_screen?: string; to_screen?: string }) =>
    post('/recorder/tap', b),
  recorderText: (b: { value: string; from_screen?: string; to_screen?: string }) =>
    post('/recorder/text', b),
  recorderKey: (b: { keycode: number; from_screen?: string; to_screen?: string }) =>
    post('/recorder/key', b),
  recorderMark: (b: { name: string; region?: [number, number, number, number] }) => post('/recorder/mark', b),
  recorderFinish: () => post<{ script_id: string; steps: number }>('/recorder/finish'),
  sync: (b: { url: string; token: string; passphrase?: string }) =>
    post<{ pushed: number; applied: number; conflicts: unknown[]; assets: number }>('/sync', b),
  events: (onEvent: (e: AgentEvent) => void) => {
    const ws = new WebSocket(BASE.replace(/^http/, 'ws') + '/ws')
    ws.onmessage = (m) => onEvent(JSON.parse(m.data))
    return () => ws.close()
  },
}
