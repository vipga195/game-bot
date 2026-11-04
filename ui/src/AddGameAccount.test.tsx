import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { AddGameAccount } from './AddGameAccount'

let games: unknown[]
const calls: { url: string; method: string; body?: string }[] = []

beforeEach(() => {
  games = []
  calls.length = 0
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    const body = typeof init?.body === 'string' ? init.body : undefined
    calls.push({ url, method: init?.method ?? 'GET', body })
    const path = new URL(url).pathname
    const data: Record<string, unknown> = {
      '/games': init?.method === 'POST' && body ? JSON.parse(body) : games,
      '/accounts': { ok: true },
    }
    return new Response(JSON.stringify(data[path] ?? { ok: true }), { status: 200 })
  }))
})
afterEach(() => vi.unstubAllGlobals())

test('saves game with still_s from form and resets to 0', async () => {
  render(<AddGameAccount />)
  await userEvent.type(screen.getByLabelText('Mã game'), 'g1')
  await userEvent.type(screen.getByLabelText('Package'), 'com.example.g1')
  expect(screen.getByLabelText('Phát hiện đứng hình (giây, 0 = tắt)')).toHaveValue(0)
  await userEvent.click(screen.getByText('Gợi ý: 180'))
  expect(screen.getByLabelText('Phát hiện đứng hình (giây, 0 = tắt)')).toHaveValue(180)
  await userEvent.click(screen.getByText('Lưu game'))
  await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.url.endsWith('/games'))).toBe(true))
  const post = calls.find((c) => c.method === 'POST' && c.url.endsWith('/games'))
  expect(JSON.parse(post?.body ?? '{}')).toEqual({ id: 'g1', package: 'com.example.g1', still_s: 180 })
  expect(screen.getByLabelText('Phát hiện đứng hình (giây, 0 = tắt)')).toHaveValue(0)
  expect(screen.getByLabelText('Mã game')).toHaveValue('')
})

test('still_s can be typed manually', async () => {
  render(<AddGameAccount />)
  await userEvent.type(screen.getByLabelText('Mã game'), 'g1')
  await userEvent.type(screen.getByLabelText('Package'), 'com.example.g1')
  await userEvent.clear(screen.getByLabelText('Phát hiện đứng hình (giây, 0 = tắt)'))
  await userEvent.type(screen.getByLabelText('Phát hiện đứng hình (giây, 0 = tắt)'), '60')
  await userEvent.click(screen.getByText('Lưu game'))
  await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.url.endsWith('/games'))).toBe(true))
  const post = calls.find((c) => c.method === 'POST' && c.url.endsWith('/games'))
  expect(JSON.parse(post?.body ?? '{}')).toEqual({ id: 'g1', package: 'com.example.g1', still_s: 60 })
})

test('re-saving an existing game keeps its still_s', async () => {
  games = [{ id: 'g1', package: 'com.example.g1', still_s: 180 }]
  render(<AddGameAccount />)
  await screen.findByRole('option', { name: 'g1' })
  await userEvent.type(screen.getByLabelText('Mã game'), 'g1')
  await userEvent.type(screen.getByLabelText('Package'), 'com.example.g1')
  expect(screen.getByLabelText('Phát hiện đứng hình (giây, 0 = tắt)')).toHaveValue(180)
  await userEvent.click(screen.getByText('Lưu game'))
  await waitFor(() => expect(calls.some((c) => c.method === 'POST' && c.url.endsWith('/games'))).toBe(true))
  const post = calls.find((c) => c.method === 'POST' && c.url.endsWith('/games'))
  expect(JSON.parse(post?.body ?? '{}').still_s).toBe(180)
})
