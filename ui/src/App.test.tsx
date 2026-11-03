import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import App from './App'
import { newRow } from './newRow'

class FakeWS { onmessage: ((m: { data: string }) => void) | null = null; close() {} }

let rows: unknown[]
const calls: { url: string; method: string; body?: string }[] = []

beforeEach(() => {
  rows = [{ ...newRow(), id: 1, name: 'r1', state: 'idle' }]
  calls.length = 0
  vi.stubGlobal('WebSocket', FakeWS)
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, method: init?.method ?? 'GET', body: init?.body as string | undefined })
    const path = new URL(url).pathname
    const data: Record<string, unknown> = {
      '/rows': init?.method === 'POST' && init.body ? JSON.parse(init.body as string) : rows,
      '/games': [{ id: 'g1', package: 'com.g' }],
      '/accounts': [],
      '/instances': [{ kind: 'ldplayer', name: 'LD0', ref: '0', serial: 'emulator-5554', running: true }],
    }
    return new Response(JSON.stringify(data[path] ?? { ok: true }), { status: 200 })
  }))
})
afterEach(() => vi.unstubAllGlobals())

test('shows rows with state and available emulators', async () => {
  render(<App />)
  expect(await screen.findByDisplayValue('r1')).toBeInTheDocument()
  expect(screen.getByText('Nghỉ')).toBeInTheDocument()
  expect(await screen.findByRole('option', { name: /LD0/ })).toBeInTheDocument()
})

test('changing priority saves reordered modes', async () => {
  render(<App />)
  await screen.findByDisplayValue('r1')
  await userEvent.click(screen.getByLabelText('Xuống event'))
  const saved = calls.filter((c) => c.method === 'POST' && c.url.endsWith('/rows')).at(-1)!
  expect(JSON.parse(saved.body!).mode_priority).toEqual(['task', 'event', 'train'])
})

test('pause button calls agent', async () => {
  render(<App />)
  await screen.findByDisplayValue('r1')
  await userEvent.click(screen.getByText('Tạm dừng'))
  await waitFor(() => expect(calls.some((c) => c.url.includes('/rows/1/pause?paused=true'))).toBe(true))
  expect(await screen.findByText('Tiếp tục')).toBeInTheDocument()
})

test('empty rows shows guidance', async () => {
  rows = []
  render(<App />)
  expect(await screen.findByText(/Chưa có dòng nào/)).toBeInTheDocument()
})

test('sync panel posts credentials to agent', async () => {
  render(<App />)
  await userEvent.click(screen.getByRole('button', { name: 'Cài đặt' }))
  await userEvent.type(screen.getByLabelText('Token'), 'tok')
  await userEvent.click(screen.getByText('Đồng bộ ngay'))
  await waitFor(() => expect(calls.some((c) => c.url.endsWith('/sync'))).toBe(true))
})

test('recorder sends text and key steps', async () => {
  rows = [{ ...newRow(), id: 1, name: 'r1', game_id: 'g1', state: 'idle' }]
  render(<App />)
  await screen.findByDisplayValue('r1')
  await userEvent.click(screen.getByLabelText('Thêm hành động'))
  await userEvent.click(screen.getByText('Ghi lại macro'))
  await userEvent.click(await screen.findByText('Quét máy'))
  await userEvent.selectOptions(await screen.findByLabelText('Máy ghi'), 'emulator-5554')
  await userEvent.click(screen.getByText('Bắt đầu ghi'))
  await userEvent.type(await screen.findByLabelText('Nội dung gõ'), 'abc def')
  await userEvent.click(screen.getByText('Gõ chữ'))
  await userEvent.click(screen.getByText('Enter'))
  await waitFor(() => expect(calls.some((c) => c.url.endsWith('/recorder/key'))).toBe(true))
  const body = (p: string) => JSON.parse(calls.find((c) => c.url.endsWith(p))!.body!)
  expect(body('/recorder/text')).toEqual({ value: 'abc def' })
  expect(body('/recorder/key')).toEqual({ keycode: 66 })
})
