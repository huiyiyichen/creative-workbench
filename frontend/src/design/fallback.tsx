'use client';

/** 兜底页：出错 / 404 / 后端没连上。 */

import Link from 'next/link';
import { useEffect, useState, type ReactNode } from 'react';
import { BASE_URL } from '@/lib/api/_core';

export type BackendState = 'checking' | 'up' | 'down';

/** 后端是否可达：任何 4xx 都算「连上了」；网络错误或网关 5xx 算没连上。 */
export async function probeBackend(timeoutMs = 4000): Promise<Exclude<BackendState, 'checking'>> {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(`${BASE_URL}/notifications/unread-count`, { signal: ctrl.signal, cache: 'no-store', credentials: 'include' });
    return res.status >= 500 ? 'down' : 'up';
  } catch {
    return 'down';
  } finally {
    clearTimeout(t);
  }
}

export function useBackendState(): [BackendState, () => void] {
  const [state, setState] = useState<BackendState>('checking');
  const check = () => {
    setState('checking');
    void probeBackend().then(setState);
  };
  useEffect(check, []);
  return [state, check];
}

export function Fallback({ code, title, children, actions }: { code?: string; title: string; children?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="cw-fallback" role="alert">
      {code ? <div className="cw-fallback-code cw-num">{code}</div> : null}
      <h1>{title}</h1>
      {children ? <div className="cw-fallback-body">{children}</div> : null}
      {actions ? <div className="cw-row">{actions}</div> : null}
    </div>
  );
}

export function HomeLink() {
  return (
    <Link className="cw-btn" data-variant="ghost" href="/">
      回今日
    </Link>
  );
}
