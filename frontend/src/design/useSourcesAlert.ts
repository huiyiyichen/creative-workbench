'use client';

import { useEffect, useState } from 'react';
import { collectionApi } from '@/lib/api/_collection';
import { hasSourceProblems } from '@/lib/collection';
import { onEvent } from '@/lib/events';

const POLL_MS = 15 * 60 * 1000; // 兜底；平时由事件流推送

/** 导航「信源」红点：有暂停 / 失败 / 可能失效的信源时亮起 */
export function useSourcesAlert(): boolean {
  const [alert, setAlert] = useState(false);
  useEffect(() => {
    let alive = true;
    const load = () => {
      collectionApi
        .health()
        .then((res) => {
          if (alive) setAlert(hasSourceProblems(res.sources));
        })
        .catch(() => undefined);
    };
    load();
    const off = onEvent<{ alert: boolean }>('sources', (d) => {
      if (alive) setAlert(d.alert);
    });
    const timer = window.setInterval(load, POLL_MS);
    return () => {
      alive = false;
      off();
      window.clearInterval(timer);
    };
  }, []);
  return alert;
}
