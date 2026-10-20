'use client';

/** 流程运行（改造方案 2.2）：发起选题研究；列出所有运行，可打开节点图、时间线、调用树。 */

import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { Input, InputNumber, Switch, message } from 'antd';
import { Suspense, useCallback, useEffect, useState } from 'react';
import { Button, Card, CwPage, Segmented, TopBar } from '@/design/components';
import { BRANCH_LABEL, STATUS_COLOR, STATUS_LABEL, fmtCost, fmtMs } from '@/design/runs';
import { runsApi, type FlowCatalogItem, type RunView } from '@/lib/api/_runs';

const FILTERS = [
  { value: '', label: '全部' },
  { value: 'running', label: '运行中' },
  { value: 'waiting', label: '等待处理' },
  { value: 'paused', label: '已暂停' },
  { value: 'done', label: '完成' },
  { value: 'failed', label: '失败' },
] as const;
type Filter = (typeof FILTERS)[number]['value'];

function StartForm({ flow, onStarted }: { flow: FlowCatalogItem; onStarted: (id: number) => void }) {
  const params = useSearchParams();
  const platformsMeta = flow.inputs.platforms;
  const [topic, setTopic] = useState(params.get('topic') || '');
  const [notes, setNotes] = useState('');
  const [platforms, setPlatforms] = useState<string[]>((platformsMeta?.default as string[]) || []);
  const [gate, setGate] = useState(true);
  const [cost, setCost] = useState<number>(flow.budget.cost ?? 2);
  const [busy, setBusy] = useState(false);
  const contentIds = (params.get('content') || '')
    .split(',')
    .map(Number)
    .filter((n) => n > 0);
  const toggle = (p: string) => setPlatforms((v) => (v.includes(p) ? v.filter((x) => x !== p) : [...v, p]));
  const start = async () => {
    setBusy(true);
    try {
      const r = await runsApi.start({
        flow_key: flow.key,
        inputs: { topic, platforms, notes: notes || undefined, content_ids: contentIds },
        gates: { choose: gate },
        budget: { cost },
      });
      onStarted(r.id);
    } catch (err) {
      message.error(err instanceof Error ? err.message : '启动失败');
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card title={`发起${flow.name}`}>
      <p className="cw-muted" style={{ marginTop: 0 }}>
        {flow.description}
      </p>
      <div className="cw-runform">
        <label>
          <span>选题</span>
          <Input value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="例如：用 AI 做一支完整的 MV" maxLength={200} />
        </label>
        <label>
          <span>补充要求</span>
          <Input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="可选：受众、平台、想避开的角度" maxLength={500} />
        </label>
        <div>
          <span>研究范围</span>
          <div className="cw-seg" role="group" aria-label="研究范围">
            {(platformsMeta?.options || []).map((p) => (
              <button key={p} type="button" aria-pressed={platforms.includes(p)} onClick={() => toggle(p)}>
                {BRANCH_LABEL[p] || p}
              </button>
            ))}
          </div>
        </div>
        <div className="cw-runform-row">
          <label className="cw-inline">
            <Switch size="small" checked={gate} onChange={setGate} /> 停下来让我选方向
          </label>
          <label className="cw-inline">
            预算上限 ¥ <InputNumber size="small" min={0.1} max={50} step={0.5} value={cost} onChange={(v) => setCost(Number(v) || 2)} />
          </label>
          {contentIds.length ? <span className="cw-muted">起点内容 {contentIds.length} 条</span> : null}
          <span className="cw-grow" />
          <Button variant="primary" disabled={busy || !topic.trim() || !platforms.length} onClick={start}>
            {busy ? '启动中…' : '开始研究'}
          </Button>
        </div>
      </div>
    </Card>
  );
}

function RunsInner() {
  const router = useRouter();
  const [flows, setFlows] = useState<FlowCatalogItem[]>([]);
  const [runs, setRuns] = useState<RunView[] | null>(null);
  const [filter, setFilter] = useState<Filter>('');

  const load = useCallback(() => {
    runsApi
      .list({ status: filter || undefined })
      .then((r) => setRuns(r.items))
      .catch(() => setRuns([]));
  }, [filter]);

  useEffect(() => {
    runsApi
      .flows()
      .then((r) => setFlows(r.items))
      .catch(() => setFlows([]));
  }, []);
  useEffect(() => {
    load();
    const t = window.setInterval(load, 5000);
    return () => window.clearInterval(t);
  }, [load]);

  const research = flows.find((f) => f.key === 'topic_research');
  return (
    <CwPage>
      <TopBar title="任务 · 流程运行" sub="每次运行都能看节点图、时间线和调用树">
        <Link href="/stats/jobs" className="cw-link-btn">
          采集与分析任务
        </Link>
        <Link href="/settings/workbench" className="cw-link-btn">
          工作台工具与 MCP
        </Link>
      </TopBar>
      <div className="cw-runs-layout">
        {research ? <StartForm flow={research} onStarted={(id) => router.push(`/runs/${id}`)} /> : null}
        <Card
          title="运行记录"
          extra={<Segmented value={filter} label="按状态筛选" options={FILTERS.map((f) => ({ value: f.value, label: f.label }))} onChange={setFilter} />}
        >
          {runs === null ? <p className="cw-muted">加载中…</p> : null}
          {runs?.length === 0 ? <p className="cw-muted">还没有运行</p> : null}
          {runs?.length ? (
            <table className="cw-table">
              <thead>
                <tr>
                  <th>运行</th>
                  <th>状态</th>
                  <th>步骤</th>
                  <th>耗时</th>
                  <th>花费</th>
                  <th>开始</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr key={r.id}>
                    <td>
                      <Link href={`/runs/${r.id}`}>{r.title}</Link>
                      {r.parent_run_id ? <span className="cw-muted"> · 分叉自 #{r.parent_run_id}</span> : null}
                    </td>
                    <td>
                      <span className="cw-runstatus" style={{ ['--st' as string]: STATUS_COLOR[r.status] }}>
                        {STATUS_LABEL[r.status]}
                      </span>
                    </td>
                    <td className="cw-num">{r.step_count ?? 0}</td>
                    <td className="cw-num">{fmtMs(r.duration_ms)}</td>
                    <td className="cw-num">
                      {fmtCost(r.cost)}
                      {r.budget.cost ? <span className="cw-muted"> / {fmtCost(r.budget.cost)}</span> : null}
                    </td>
                    <td className="cw-num cw-muted">{new Date(r.created_at).toLocaleString('zh-CN', { hour12: false })}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
        </Card>
      </div>
    </CwPage>
  );
}

export default function RunsPage() {
  return (
    <Suspense>
      <RunsInner />
    </Suspense>
  );
}
