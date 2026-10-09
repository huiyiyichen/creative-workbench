import { afterEach, describe, expect, it, vi } from 'vitest';
import { request } from '@/lib/api/_core';

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('bounded API requests', () => {
  it('returns JSON and clears the deadline after success', async () => {
    vi.useFakeTimers();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{"ok":true}')));
    await expect(request('/studio/catalog', { timeoutMs: 1000 })).resolves.toEqual({ ok: true });
    expect(vi.getTimerCount()).toBe(0);
  });

  it('aborts a stalled connection and exposes a retryable timeout', async () => {
    vi.useFakeTimers();
    vi.stubGlobal('fetch', vi.fn((_url, init: RequestInit) => new Promise((_resolve, reject) => {
      init.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
    })));
    const pending = request('/studio/projects', { timeoutMs: 1000 });
    const assertion = expect(pending).rejects.toThrow('请求超时，请重试');
    await vi.advanceTimersByTimeAsync(1000);
    await assertion;
    expect(vi.getTimerCount()).toBe(0);
  });

  it('keeps the deadline active until the response body has loaded', async () => {
    vi.useFakeTimers();
    vi.stubGlobal('fetch', vi.fn((_url, init: RequestInit) => Promise.resolve({
      ok: true, status: 200,
      text: () => new Promise((_resolve, reject) => {
        init.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
      }),
    })));
    const pending = request('/studio/projects', { timeoutMs: 1000 });
    const assertion = expect(pending).rejects.toThrow('请求超时，请重试');
    await vi.advanceTimersByTimeAsync(1000);
    await assertion;
  });

  it('propagates caller cancellation without misreporting it as a timeout', async () => {
    const caller = new AbortController();
    vi.stubGlobal('fetch', vi.fn((_url, init: RequestInit) => new Promise((_resolve, reject) => {
      init.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
    })));
    const pending = request('/studio/catalog', { signal: caller.signal, timeoutMs: 1000 });
    const assertion = expect(pending).rejects.toThrow('Aborted');
    caller.abort();
    await assertion;
  });

  it('does not change untimed long-running requests', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response('{"result":"done"}'));
    vi.stubGlobal('fetch', fetch);
    await expect(request('/daily-reports/generate', { method: 'POST' })).resolves.toEqual({ result: 'done' });
    expect(fetch.mock.calls[0][1].signal).toBeUndefined();
  });
});
