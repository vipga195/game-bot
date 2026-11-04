import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { NotifyPanel } from './NotifyPanel'

let channels: unknown[]
const calls: { url: string; method: string; body?: string }[] = []

beforeEach(() => {
  channels = [{ id: 'n1', kind: 'telegram', name: 'Bot chính', level: 'error', enabled: true, config: { chat_id: '-100123' } }]
  calls.length = 0
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    const body = typeof init?.body === 'string' ? init.body : undefined
    calls.push({ url, method: init?.method ?? 'GET', body })
    const path = new URL(url).pathname
    const data: Record<string, unknown> = {
      '/notify/channels': init?.method === 'POST' && body ? JSON.parse(body) : channels,
      '/notify/test': { ok: true },
      '/notify/channels/n1': { ok: true },
    }
    return new Response(JSON.stringify(data[path] ?? { ok: true }), { status: 200 })
  }))
})
afterEach(() => vi.unstubAllGlobals())

test('lists channels from GET', async () => {
  render(<NotifyPanel />)
  expect(await screen.findByText('Bot chính')).toBeInTheDocument()
  expect(screen.getByText('-100123').parentElement).toHaveTextContent('Chỉ lỗi')
})

test('shows empty state when no channels', async () => {
  channels = []
  render(<NotifyPanel />)
  expect(await screen.findByText('Chưa có kênh nào. Thêm kênh Telegram để nhận báo lỗi.')).toBeInTheDocument()
})

test('adding sends POST body and clears token', async () => {
  render(<NotifyPanel />)
  await userEvent.type(screen.getByLabelText('Tên kênh'), 'Bot phụ')
  await userEvent.type(screen.getByLabelText('Bot token'), 'secret123')
  await userEvent.type(screen.getByLabelText('Chat id'), '-100999')
  await userEvent.selectOptions(screen.getByLabelText('Mức báo'), 'Lỗi và cảnh báo')
  await userEvent.click(screen.getByText('Thêm kênh'))
  await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.url.endsWith('/notify/channels'))).toBe(true))
  const post = calls.find((c) => c.method === 'POST' && c.url.endsWith('/notify/channels'))
  expect(JSON.parse(post?.body ?? '{}')).toEqual({
    kind: 'telegram',
    name: 'Bot phụ',
    level: 'all',
    config: { chat_id: '-100999', send_image: false },
    secret: 'secret123',
  })
  expect(screen.getByLabelText('Tên kênh')).toHaveValue('')
  expect(screen.getByRole('status')).toHaveClass('ok')
  expect(screen.getByLabelText('Bot token')).toHaveValue('')
})

test('test button calls POST /notify/test and shows result', async () => {
  render(<NotifyPanel />)
  await waitFor(() => expect(screen.getByText('Bot chính')).toBeInTheDocument())
  await userEvent.click(screen.getByText('Gửi thử'))
  await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.url.endsWith('/notify/test'))).toBe(true))
  const testCall = calls.find((c) => c.url.endsWith('/notify/test'))
  expect(JSON.parse(testCall?.body ?? '{}')).toEqual({ id: 'n1' })
  expect(await screen.findByText('Đã gửi')).toBeInTheDocument()
})

test('delete calls DELETE after confirm', async () => {
  vi.spyOn(window, 'confirm').mockReturnValue(true)
  render(<NotifyPanel />)
  await waitFor(() => expect(screen.getByText('Bot chính')).toBeInTheDocument())
  await userEvent.click(screen.getByText('Xoá'))
  await waitFor(() => expect(calls.some((c) => c.method === 'DELETE' && c.url.endsWith('/notify/channels/n1'))).toBe(true))
})

test('teams sends webhook as secret and empty config', async () => {
  render(<NotifyPanel />)
  await userEvent.selectOptions(screen.getByLabelText('Loại kênh'), 'Teams')
  await userEvent.type(screen.getByLabelText('Tên kênh'), 'Bot Teams')
  await userEvent.type(screen.getByLabelText('Webhook URL'), 'https://example.com/hook')
  await userEvent.click(screen.getByText('Thêm kênh'))
  await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.url.endsWith('/notify/channels'))).toBe(true))
  const post = calls.find((c) => c.method === 'POST' && c.url.endsWith('/notify/channels'))
  expect(JSON.parse(post?.body ?? '{}')).toEqual({
    kind: 'teams',
    name: 'Bot Teams',
    level: 'error',
    config: {},
    secret: 'https://example.com/hook',
  })
  expect(screen.getByLabelText('Webhook URL')).toHaveValue('')
})

test('zalo sends chat_id and secret', async () => {
  render(<NotifyPanel />)
  await userEvent.selectOptions(screen.getByLabelText('Loại kênh'), 'Zalo')
  await userEvent.type(screen.getByLabelText('Tên kênh'), 'Bot Zalo')
  await userEvent.type(screen.getByLabelText('Bot token'), 'secret123')
  await userEvent.type(screen.getByLabelText('Chat id'), '-100999')
  await userEvent.click(screen.getByText('Thêm kênh'))
  await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.url.endsWith('/notify/channels'))).toBe(true))
  const post = calls.find((c) => c.method === 'POST' && c.url.endsWith('/notify/channels'))
  expect(JSON.parse(post?.body ?? '{}')).toEqual({
    kind: 'zalo',
    name: 'Bot Zalo',
    level: 'error',
    config: { chat_id: '-100999' },
    secret: 'secret123',
  })
})

test('facebook sends page_id, recipient_id and secret', async () => {
  render(<NotifyPanel />)
  await userEvent.selectOptions(screen.getByLabelText('Loại kênh'), 'Facebook')
  await userEvent.type(screen.getByLabelText('Tên kênh'), 'Bot Facebook')
  await userEvent.type(screen.getByLabelText('Page access token'), 'token123')
  await userEvent.type(screen.getByLabelText('Page id'), 'page123')
  await userEvent.type(screen.getByLabelText('Recipient id (PSID)'), 'recipient123')
  await userEvent.click(screen.getByText('Thêm kênh'))
  await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.url.endsWith('/notify/channels'))).toBe(true))
  const post = calls.find((c) => c.method === 'POST' && c.url.endsWith('/notify/channels'))
  expect(JSON.parse(post?.body ?? '{}')).toEqual({
    kind: 'facebook',
    name: 'Bot Facebook',
    level: 'error',
    config: { page_id: 'page123', recipient_id: 'recipient123' },
    secret: 'token123',
  })
  expect(screen.getByLabelText('Page access token')).toHaveValue('')
  expect(await screen.findByText(/24 giờ/)).toBeInTheDocument()
})

test('switching kind shows that kind\'s fields', async () => {
  render(<NotifyPanel />)
  await userEvent.selectOptions(screen.getByLabelText('Loại kênh'), 'Facebook')
  expect(await screen.findByLabelText('Page id')).toBeInTheDocument()
  expect(screen.queryByLabelText('Chat id')).not.toBeInTheDocument()
  await userEvent.selectOptions(screen.getByLabelText('Loại kênh'), 'Teams')
  expect(screen.queryByLabelText('Bot token')).not.toBeInTheDocument()
  expect(await screen.findByLabelText('Webhook URL')).toBeInTheDocument()
})

test('delete aborted when confirm is false', async () => {
  vi.spyOn(window, 'confirm').mockReturnValue(false)
  render(<NotifyPanel />)
  await waitFor(() => expect(screen.getByText('Bot chính')).toBeInTheDocument())
  await userEvent.click(screen.getByText('Xoá'))
  expect(calls.some((c) => c.method === 'DELETE')).toBe(false)
})

test('telegram send_image checkbox defaults off, warns, and is sent when checked', async () => {
  render(<NotifyPanel />)
  const box = screen.getByLabelText('Gửi kèm ảnh chụp màn hình lỗi')
  expect(box).not.toBeChecked()
  expect(screen.getByText(/Ảnh có thể chứa thông tin nhạy cảm/)).toBeInTheDocument()
  await userEvent.click(box)
  await userEvent.type(screen.getByLabelText('Tên kênh'), 'Bot ảnh')
  await userEvent.type(screen.getByLabelText('Bot token'), 's')
  await userEvent.type(screen.getByLabelText('Chat id'), '1')
  await userEvent.click(screen.getByText('Thêm kênh'))
  await waitFor(() => expect(calls.some((c) => c.method === 'POST')).toBe(true))
  const post = calls.find((c) => c.method === 'POST')
  expect(JSON.parse(post?.body ?? '{}').config).toEqual({ chat_id: '1', send_image: true })
})
