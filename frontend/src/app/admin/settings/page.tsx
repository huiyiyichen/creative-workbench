'use client';

import React, { useEffect, useState } from 'react';
import { Plus, Settings, Trash2, Webhook } from 'lucide-react';
import { settingsApi } from '@/lib/api';
import type { NotificationWebhookConfig, WebhookItem, WebhookItemUpdate } from '@/lib/api/_analytics';
import { Badge, Button, Panel } from '@/components/ui';
import { AdminPageShell, AdminPageHeader, AdminNoticeBanner } from '@/components/admin-ui';
import { LoadingState } from '@/components/StateView';

export default function AdminSettingsPage() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [config, setConfig] = useState<NotificationWebhookConfig | null>(null);
  const [webhooks, setWebhooks] = useState<WebhookItemUpdate[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    const data = await settingsApi.getNotificationWebhook();
    setConfig(data);
    setWebhooks(data.webhooks.map((item: WebhookItem) => ({
      name: item.name,
      enabled: item.enabled,
      webhook_url: '',
      event_types: item.event_types?.length ? item.event_types : ['source_failure'],
      note: item.note,
    })));
  };

  useEffect(() => {
    void load().catch(() => setError('加载失败')).finally(() => setLoading(false));
  }, []);

  const updateWebhook = (index: number, patch: Partial<WebhookItemUpdate>) => {
    setWebhooks((items) => items.map((item, current) => current === index ? { ...item, ...patch } : item));
  };

  const save = async () => {
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      await settingsApi.updateNotificationWebhook({ webhooks });
      await load();
      setNotice('已保存');
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存失败');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <AdminPageShell maxWidth={860}><LoadingState label="加载中…" minHeight="200px" panel /></AdminPageShell>;
  }

  return (
    <AdminPageShell maxWidth={860}>
      <AdminPageHeader title="工作区设置" icon={Settings} description="来源与通知" />
      <Panel className="p-6">
        <div className="mb-5 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Webhook size={16} className="text-gray-500" />
            <h2 className="text-base font-black text-gray-900">通知 webhook</h2>
          </div>
          <div className="flex items-center gap-2">
            {config?.webhooks.some((item) => item.enabled && item.webhook_url_configured) ? (
              <Badge tone="teal">已启用</Badge>
            ) : <Badge tone="neutral">未配置</Badge>}
            <Button
              variant="ghost"
              className="!px-2 !py-1 text-xs"
              onClick={() => setWebhooks((items) => [...items, {
                name: '',
                enabled: true,
                webhook_url: '',
                event_types: ['source_failure'],
                note: '',
              }])}
            >
              <Plus size={12} /> 添加
            </Button>
          </div>
        </div>
        {webhooks.length === 0 ? (
          <div className="rounded-sm border border-dashed border-gray-200 py-10 text-center text-xs text-gray-400">暂无配置</div>
        ) : (
          <div className="space-y-4">
            {webhooks.map((item, index) => {
              const original = config?.webhooks[index];
              return (
                <div key={`${item.name}-${index}`} className="rounded-sm border border-gray-200 p-4">
                  <div className="mb-3 flex items-center justify-between gap-3">
                    <div className="flex min-w-0 items-center gap-2">
                      <input type="checkbox" checked={item.enabled} onChange={(event) => updateWebhook(index, { enabled: event.target.checked })} />
                      <input value={item.name} onChange={(event) => updateWebhook(index, { name: event.target.value })} placeholder="名称" className="h-8 min-w-0 flex-1 rounded-sm border border-gray-200 px-2 text-sm" />
                    </div>
                    <button type="button" className="text-gray-400 hover:text-red-500" title="删除" onClick={() => setWebhooks((items) => items.filter((_, current) => current !== index))}>
                      <Trash2 size={14} />
                    </button>
                  </div>
                  <label className="grid gap-1 text-xs font-bold text-gray-500">
                    Webhook URL
                    <input type="password" value={item.webhook_url} onChange={(event) => updateWebhook(index, { webhook_url: event.target.value })} placeholder={original?.webhook_url_configured ? `已配置（${original.webhook_url_preview}****）` : '粘贴地址'} className="h-9 rounded-sm border border-gray-200 px-3 text-sm font-normal" />
                  </label>
                  <label className="mt-3 grid gap-1 text-xs font-bold text-gray-500">
                    备注
                    <input value={item.note} onChange={(event) => updateWebhook(index, { note: event.target.value })} className="h-9 rounded-sm border border-gray-200 px-3 text-sm font-normal" />
                  </label>
                </div>
              );
            })}
          </div>
        )}
        {error && <AdminNoticeBanner tone="red" onClose={() => setError(null)}>{error}</AdminNoticeBanner>}
        {notice && <AdminNoticeBanner tone="teal" onClose={() => setNotice(null)}>{notice}</AdminNoticeBanner>}
        <div className="mt-5 flex justify-end">
          <Button variant="primary" onClick={() => void save()} disabled={saving}>{saving ? '保存中…' : '保存'}</Button>
        </div>
      </Panel>
    </AdminPageShell>
  );
}
