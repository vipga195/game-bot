import type { Row } from './api'

export const newRow = (): Row => ({
  name: 'Dòng mới',
  emulator_kind: '',
  emulator_ref: '',
  game_id: '',
  account_id: '',
  mode_priority: ['event', 'task', 'train'],
  schedule: {
    active_from: '00:00', active_to: '23:59', utc_offset_min: -new Date().getTimezoneOffset(),
    interval_min: { task: 120, train: 60 }, event_at: {}, event_window_min: 30, event_lead_min: 2, last_run: {},
  },
  enabled: true,
})
