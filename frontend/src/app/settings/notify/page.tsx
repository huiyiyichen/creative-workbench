'use client';

/** 设置 · 通知：最近 20 次推送（原 Webhook 日志页删除，11.2）。推送地址在「系统」里配置。 */

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { Card, StatusDot } from '@/design/components';
import { dailyReportApi, type WebhookDeliveryLogItem } from '@/lib/api/_daily-reports';

export default function NotifySettingsPage() {
  const [items, setItems] = useState<WebhookDeliveryLogItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    dailyReportApi
      .listWebhookLogs({ limit: 20 })
      .then((r) => setItems(r.items))
      .catch((err) => setError(err instanceof Error ? err.message : '请求失败'));
  }, []);

  return (
    <Card title="最近 20 次推送" extra={<Link href="/admin/settings" className="cw-muted">配置推送地址</Link>}>
      {error ? <div className="cw-error">{error}</div> : null}
      {!items ? (
        <div className="cw-muted">加载中…</div>
      ) : items.length === 0 ? (
        <div className="cw-muted">还没有推送记录</div>
      ) : (
        <table className="cw-table">
          <thead>
            <tr>
              <th>时间</th>
              <th>类型</th>
              <th>标题</th>
              <th>结果</th>
              <th>耗时</th>
            </tr>
          </thead>
          <tbody>
            {items.map((l) => (
              <tr key={l.id}>
                <td className="cw-num">{l.created_at ? new Date(l.created_at).toLocaleString('zh-CN', { hour12: false }) : '—'}</td>
                <td>{l.event_type}</td>
                <td>{l.title}</td>
                <td>
                  <StatusDot tone={l.success ? 'ok' : 'bad'} /> {l.success ? `成功 ${l.status_code ?? ''}` : l.error_message || `失败 ${l.status_code ?? ''}`}
                </td>
                <td className="cw-num">{l.duration_ms} ms</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}
