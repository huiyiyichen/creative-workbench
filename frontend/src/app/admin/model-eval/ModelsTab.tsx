'use client';

/**
 * 模型配置（调色台样式）：按路由组分段，每组按优先级从上到下就是调用顺序（路由链）。
 * 每行：顺位、名称与实际请求的模型串、接口与渠道、状态灯（启用 / 缺 Key / 停用）、单价、最近一次测试、操作。
 * 添加 / 编辑仍用 ModelEditForm 弹窗；添加保存后自动测一次连接。
 */

import React, { useMemo, useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { Button, Card } from '@/design/components';
import { EmptyInstrument, StatusLamp, type LampTone } from '@/design/instrument';
import { confirmAction } from '@/design/feedback';
import { modelsApi } from '@/lib/api';
import type { LlmModelItem } from '@/lib/api';
import { formatPerMillion } from './_model-eval-utils';
import { ModelEditForm } from './ModelEditForm';

type TestResult = { status: string; response?: string; note?: string; error?: string; duration_ms: number };

function lamp(m: LlmModelItem): { tone: LampTone; label: string } {
  if (!m.enabled) return { tone: 'off', label: '停用' };
  if (!m.api_key_set && m.api_base) return { tone: 'warn', label: '缺 Key' };
  return { tone: 'ok', label: '启用' };
}

function TestLine({ r }: { r: TestResult }) {
  if (r.status === 'success') {
    return (
      <span className="cw-model-test" data-tone="ok">
        通 · <span className="cw-num">{r.duration_ms} ms</span>
        {r.note ? <small>{r.note}</small> : null}
      </span>
    );
  }
  return (
    <span className="cw-model-test" data-tone="bad" title={r.error}>
      不通 · {(r.error || '').slice(0, 120)}
    </span>
  );
}

export function ModelsTab({ models, onRefresh }: { models: LlmModelItem[]; onRefresh: () => void }) {
  const [editing, setEditing] = useState<LlmModelItem | null>(null);
  const [testing, setTesting] = useState<number | null>(null);
  const [testResult, setTestResult] = useState<Record<number, TestResult>>({});
  const [showAdd, setShowAdd] = useState(false);

  const groups = useMemo(() => {
    const by = new Map<string, LlmModelItem[]>();
    for (const m of models) {
      const g = m.routing_group || 'default';
      by.set(g, [...(by.get(g) || []), m]);
    }
    return [...by.entries()]
      .sort(([a], [b]) => (a === 'default' ? -1 : b === 'default' ? 1 : a.localeCompare(b)))
      .map(([g, list]) => [g, list.sort((a, b) => Number(b.enabled) - Number(a.enabled) || a.routing_priority - b.routing_priority || a.id - b.id)] as const);
  }, [models]);

  const handleTest = async (id: number) => {
    setTesting(id);
    try {
      const res = await modelsApi.test(id);
      setTestResult((prev) => ({ ...prev, [id]: res }));
    } catch (e: unknown) {
      setTestResult((prev) => ({ ...prev, [id]: { status: 'failed', error: e instanceof Error ? e.message : String(e), duration_ms: 0 } }));
    }
    setTesting(null);
  };

  const handleToggle = async (m: LlmModelItem) => {
    await modelsApi.update(m.id, { enabled: !m.enabled });
    onRefresh();
  };

  const handleDelete = async (m: LlmModelItem) => {
    if (!(await confirmAction({ title: `删除模型「${m.name}」？`, danger: true }))) return;
    await modelsApi.delete(m.id);
    onRefresh();
  };

  return (
    <div className="cw-models">
      {showAdd && (
        <ModelEditForm
          onClose={(saved, createdId) => {
            setShowAdd(false);
            onRefresh();
            if (saved && createdId) void handleTest(createdId);
          }}
        />
      )}
      {editing && (
        <ModelEditForm
          model={editing}
          onClose={() => {
            setEditing(null);
            onRefresh();
          }}
        />
      )}

      {models.length === 0 ? (
        showAdd ? null : (
          <EmptyInstrument
            kind="unplugged"
            title="还没有模型"
            reason="日报、选题分析、写稿和改写都要用到语言模型。填一个 API Key 就能开始，之后可以再加备用模型做路由。"
            actions={
              <Button variant="primary" icon={<Plus size={14} />} onClick={() => setShowAdd(true)}>
                添加模型
              </Button>
            }
          />
        )
      ) : (
        <>
          <div className="cw-filters">
            <span className="cw-muted">同一路由组里从上到下依次调用：前一个失败或限流就自动换下一个。停用的不参与自动任务和测评。</span>
            <span className="cw-grow" />
            <Button variant="primary" icon={<Plus size={14} />} onClick={() => setShowAdd(true)}>
              添加模型
            </Button>
          </div>
          {groups.map(([group, list]) => (
            <Card key={group} title={group === 'default' ? '默认路由' : `路由组 · ${group}`} extra={<small className="cw-muted cw-num">{list.filter((m) => m.enabled).length} / {list.length} 启用</small>}>
              <ol className="cw-model-rows">
                {list.map((m, i) => {
                  const st = lamp(m);
                  return (
                    <li key={m.id} className="cw-model-row" data-off={m.enabled ? undefined : 'true'}>
                      <span className="cw-model-rank cw-num" title={`优先级 ${m.routing_priority}`}>
                        {m.enabled ? i + 1 : '—'}
                      </span>
                      <div className="cw-model-name">
                        <b>{m.name}</b>
                        <small className="cw-num" title={m.resolved_model}>
                          {m.resolved_model || m.model_id}
                        </small>
                      </div>
                      <div className="cw-model-meta">
                        <span>{m.provider}</span>
                        <small>
                          {m.channel_name || m.api_base || '官方接口'}
                          {m.model_family ? ` · ${m.model_family}` : ''}
                        </small>
                      </div>
                      <div className="cw-model-meta">
                        <span className="cw-num">
                          {m.cost_per_1m_input == null && m.cost_per_1m_output == null
                            ? '单价未填'
                            : `入 ${formatPerMillion(m.cost_per_1m_input)} · 出 ${formatPerMillion(m.cost_per_1m_output)}`}
                        </span>
                        <small className="cw-num">
                          {m.max_tokens} tok · {m.requests_per_minute}/分
                        </small>
                      </div>
                      <div className="cw-model-state">
                        <StatusLamp tone={st.tone} label={st.label} />
                        {testResult[m.id] ? <TestLine r={testResult[m.id]} /> : null}
                      </div>
                      <div className="cw-model-acts">
                        <Button onClick={() => handleTest(m.id)} disabled={testing === m.id}>
                          {testing === m.id ? '测试中…' : '测试'}
                        </Button>
                        <Button variant="ghost" onClick={() => setEditing(m)}>
                          编辑
                        </Button>
                        <Button variant="ghost" onClick={() => handleToggle(m)}>
                          {m.enabled ? '停用' : '启用'}
                        </Button>
                        <Button variant="ghost" size="icon" aria-label={`删除 ${m.name}`} title="删除" onClick={() => handleDelete(m)} icon={<Trash2 size={14} />} />
                      </div>
                    </li>
                  );
                })}
              </ol>
            </Card>
          ))}
        </>
      )}
    </div>
  );
}
