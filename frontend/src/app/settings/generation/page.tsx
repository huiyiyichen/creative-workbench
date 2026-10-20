'use client';

/** 设置 · 生成服务（改造方案第 8 节）：名称、类型、接口格式、地址、Key（本地加密）、模型、能力、单价、每日上限。 */

import { Input, InputNumber, Modal, Select, Switch, message } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import { Button, Card } from '@/design/components';
import { genApi, type GenService } from '@/lib/api/_generations';

interface FormState {
  id?: number;
  name: string;
  base_url: string;
  model: string;
  api_key: string;
  unit_price: number;
  daily_limit: number | null;
  refs: boolean;
  max_n: number;
  is_default: boolean;
  enabled: boolean;
}

const EMPTY: FormState = {
  name: '',
  base_url: 'https://api.openai.com/v1',
  model: 'gpt-image-1',
  api_key: '',
  unit_price: 0.3,
  daily_limit: 10,
  refs: true,
  max_n: 4,
  is_default: true,
  enabled: true,
};

function errText(err: unknown): string {
  return err instanceof Error ? err.message : '请求失败';
}

export default function GenerationSettingsPage() {
  const [items, setItems] = useState<GenService[] | null>(null);
  const [form, setForm] = useState<FormState | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const load = useCallback(async () => {
    try {
      setItems((await genApi.services()).items);
    } catch (err) {
      message.error(errText(err));
      setItems([]);
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);

  const edit = (s?: GenService) =>
    setForm(
      s
        ? {
            id: s.id,
            name: s.name,
            base_url: s.base_url,
            model: s.model,
            api_key: '',
            unit_price: s.unit_price,
            daily_limit: s.daily_limit,
            refs: Boolean(s.capabilities.refs),
            max_n: s.capabilities.max_n || 4,
            is_default: s.is_default,
            enabled: s.enabled,
          }
        : { ...EMPTY, is_default: !items?.length },
    );

  const save = async () => {
    if (!form) return;
    setBusy('save');
    try {
      const body = {
        name: form.name,
        kind: 'image' as const,
        api_format: 'openai_images' as const,
        base_url: form.base_url,
        model: form.model,
        unit_price: form.unit_price,
        daily_limit: form.daily_limit,
        capabilities: { refs: form.refs, max_n: form.max_n },
        is_default: form.is_default,
        enabled: form.enabled,
        ...(form.api_key ? { api_key: form.api_key } : {}),
      };
      if (form.id) await genApi.updateService(form.id, body);
      else await genApi.createService(body);
      setForm(null);
      message.success('已保存');
      await load();
    } catch (err) {
      message.error(errText(err));
    } finally {
      setBusy(null);
    }
  };

  const test = async (s: GenService) => {
    setBusy(`test-${s.id}`);
    try {
      const r = await genApi.testService(s.id);
      if (r.ok) message.success('连接正常，已生成一张测试图');
      else message.error(r.error || '测试失败');
      await load();
    } catch (err) {
      message.error(errText(err));
    } finally {
      setBusy(null);
    }
  };

  const remove = async (s: GenService) => {
    if (!window.confirm(`删除「${s.name}」？已生成的图不受影响。`)) return;
    await genApi.deleteService(s.id).catch((err) => message.error(errText(err)));
    await load();
  };

  return (
    <div className="cw-stack">
      <Card title="生图服务" extra={<Button onClick={() => edit()}>添加服务</Button>}>
        {items === null ? (
          <p className="cw-muted">加载中…</p>
        ) : items.length ? (
          <table className="cw-table">
            <thead>
              <tr>
                <th>名称</th>
                <th>模型</th>
                <th>地址</th>
                <th>Key</th>
                <th>参考图</th>
                <th>单价</th>
                <th>今日 / 上限</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {items.map((s) => (
                <tr key={s.id} style={{ opacity: s.enabled ? 1 : 0.5 }}>
                  <td>
                    {s.name}
                    {s.is_default ? <small className="cw-muted"> · 默认</small> : null}
                  </td>
                  <td className="cw-num">{s.model}</td>
                  <td className="cw-muted" style={{ maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {s.base_url}
                  </td>
                  <td className="cw-num">{s.key_hint || '—'}</td>
                  <td>{s.capabilities.refs ? '支持' : '—'}</td>
                  <td className="cw-num">¥{s.unit_price.toFixed(2)} / 张</td>
                  <td className="cw-num">
                    ¥{s.spent_today.toFixed(2)} / {s.daily_limit != null ? `¥${s.daily_limit.toFixed(2)}` : '不限'}
                  </td>
                  <td style={{ whiteSpace: 'nowrap' }}>
                    <button type="button" className="cw-link-btn" onClick={() => test(s)} disabled={busy !== null}>
                      {busy === `test-${s.id}` ? '测试中…' : '测试'}
                    </button>
                    <button type="button" className="cw-link-btn" onClick={() => edit(s)}>
                      编辑
                    </button>
                    <button type="button" className="cw-link-btn" onClick={() => remove(s)}>
                      删除
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="cw-empty">还没有生成服务。添加一个 OpenAI 兼容的图像接口（例如 image2.5、gpt-image-1）后，情绪板、配图、封面和分镜关键帧就能生图。</p>
        )}
        <p className="cw-muted" style={{ fontSize: 12 }}>
          Key 只加密保存在本机。每日上限按单价 × 张数计算，超过时生图会被拒绝。没选中的候选图保留 7 天。
        </p>
      </Card>
      <Modal
        open={form !== null}
        title={form?.id ? '编辑生成服务' : '添加生成服务'}
        onCancel={() => setForm(null)}
        onOk={save}
        okText="保存"
        cancelText="取消"
        confirmLoading={busy === 'save'}
        destroyOnHidden
      >
        {form ? (
          <div className="cw-brief">
            <label>
              <span>名称</span>
              <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} maxLength={100} placeholder="例如 image2.5" />
            </label>
            <label>
              <span>接口格式</span>
              <Select value="openai_images" options={[{ value: 'openai_images', label: 'OpenAI 兼容图像接口' }]} />
            </label>
            <label className="cw-brief-wide">
              <span>地址</span>
              <Input value={form.base_url} onChange={(e) => setForm({ ...form, base_url: e.target.value })} placeholder="https://…/v1" />
            </label>
            <label>
              <span>模型</span>
              <Input value={form.model} onChange={(e) => setForm({ ...form, model: e.target.value })} />
            </label>
            <label>
              <span>Key{form.id ? '（留空不改）' : ''}</span>
              <Input.Password value={form.api_key} onChange={(e) => setForm({ ...form, api_key: e.target.value })} autoComplete="off" />
            </label>
            <label>
              <span>单价（元 / 张）</span>
              <InputNumber min={0} max={100} step={0.05} value={form.unit_price} onChange={(v) => setForm({ ...form, unit_price: Number(v) || 0 })} />
            </label>
            <label>
              <span>每日上限（元，空为不限）</span>
              <InputNumber min={0} max={10000} value={form.daily_limit ?? undefined} onChange={(v) => setForm({ ...form, daily_limit: v == null ? null : Number(v) })} />
            </label>
            <label>
              <span>一次最多张数</span>
              <InputNumber min={1} max={8} value={form.max_n} onChange={(v) => setForm({ ...form, max_n: Number(v) || 1 })} />
            </label>
            <label className="cw-inline">
              <Switch size="small" checked={form.refs} onChange={(v) => setForm({ ...form, refs: v })} /> 支持参考图（/images/edits）
            </label>
            <label className="cw-inline">
              <Switch size="small" checked={form.is_default} onChange={(v) => setForm({ ...form, is_default: v })} /> 设为默认
            </label>
            <label className="cw-inline">
              <Switch size="small" checked={form.enabled} onChange={(v) => setForm({ ...form, enabled: v })} /> 启用
            </label>
          </div>
        ) : null}
      </Modal>
    </div>
  );
}
