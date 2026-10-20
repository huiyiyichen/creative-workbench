'use client';

/** 「记入飞书」按钮：没写过就新建记录，写过就更新；显示上次同步结果。未配置时引导去设置。 */

import Link from 'next/link';
import { message } from 'antd';
import { useEffect, useState } from 'react';
import { feishuApi, type FeishuRecord } from '@/lib/api/_feishu';

export function FeishuButton({ type, id, className = 'cw-btn' }: { type: 'content' | 'project'; id: number; className?: string }) {
  const [configured, setConfigured] = useState<boolean | null>(null);
  const [rec, setRec] = useState<FeishuRecord | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let alive = true;
    feishuApi
      .settings()
      .then((s) => {
        if (!alive) return;
        setConfigured(s.configured);
        if (s.configured) feishuApi.get(type, id).then((r) => alive && setRec(r.record)).catch(() => {});
      })
      .catch(() => alive && setConfigured(false));
    return () => {
      alive = false;
    };
  }, [type, id]);
  if (configured === null) return null;
  if (!configured) {
    return (
      <Link className={className} data-variant="ghost" href="/settings/feishu" title="先在设置里连上飞书多维表格">
        记入飞书
      </Link>
    );
  }
  const run = async () => {
    setBusy(true);
    try {
      const r = await feishuApi.record(type, id);
      setRec(r);
      message.success(r.skipped_columns?.length ? `已记入飞书（表格里没有：${r.skipped_columns.join('、')}）` : rec?.record_id ? '已更新飞书记录' : '已记入飞书');
    } catch (err) {
      message.error(err instanceof Error ? err.message : '记入飞书失败');
      feishuApi.get(type, id).then((r) => setRec(r.record)).catch(() => {});
    } finally {
      setBusy(false);
    }
  };
  const title = rec?.status === 'failed' ? `上次失败：${rec.error || ''}` : rec?.synced_at ? `已记入，${new Date(rec.synced_at).toLocaleString('zh-CN', { hour12: false })} 同步` : '写进飞书多维表格';
  return (
    <button type="button" className={className} data-variant="ghost" onClick={run} disabled={busy} title={title} data-state={rec?.status}>
      {busy ? '写入中…' : rec?.status === 'synced' ? '已记入飞书' : rec?.status === 'failed' ? '重试记入飞书' : '记入飞书'}
    </button>
  );
}
