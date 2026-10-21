'use client';

/**
 * 运行视图部件（创作工作台设计 7.1 / 改造方案 2.3）：
 * RunGraph 节点图（达芬奇调色页节点样式）、RunTimeline 时间线、TraceTree 调用树、StepDetail 节点详情、
 * GatePanel 人工关卡、ArtifactBody 产物（简报条目带出处、方向卡）。
 */

import Link from 'next/link';
import { Input, message, Modal, Select } from 'antd';
import { Background, Handle, Position, ReactFlow, type Edge, type Node, type NodeProps } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { Bot, ChevronDown, ChevronRight, GitBranch, User, Wrench } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Button } from '@/design/components';
import { color } from '@/design/tokens';
import {
  nodeStatus,
  nodeSteps,
  runsApi,
  type ArtifactView,
  type DirectionCard,
  type FlowGraph,
  type RunDetail,
  type SourceRef,
  type SpanView,
  type StepDetail as StepDetailData,
  type StepStatus,
  type StepView,
  type TraceStep,
} from '@/lib/api/_runs';

export const STATUS_COLOR: Record<string, string> = {
  pending: color.line,
  queued: color.line,
  running: color.bl,
  done: color.gr,
  failed: color.rd,
  waiting: color.yl,
  paused: color.yl,
  reused: color.dim,
  stopped: color.faint,
};

export const STATUS_LABEL: Record<string, string> = {
  pending: '未开始',
  queued: '排队',
  running: '运行中',
  done: '完成',
  failed: '失败',
  waiting: '等待处理',
  paused: '已暂停',
  reused: '复用',
  stopped: '已停止',
};

export const ROLE_LABEL: Record<string, string> = {
  researcher: '研究员',
  aggregator: '汇总',
  planner: '策划',
  gate: '关卡',
};

export const EXECUTOR_LABEL: Record<string, string> = {
  internal: '已配模型',
  deepseek_harness: 'DeepSeek Harness',
  claude_code: 'Claude Code',
  codex: 'Codex',
  human: '你',
};

export const BRANCH_LABEL: Record<string, string> = {
  library: '灵感库',
  bilibili: 'B站',
  youtube: 'YouTube',
  hn: 'HN',
  reddit: 'Reddit',
  github: 'GitHub',
  web: '网页',
};

export function fmtMs(ms: number | null | undefined): string {
  if (ms == null) return '—';
  if (ms < 1000) return `${ms}ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1)}s`;
  return `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')}`;
}

export function fmtCost(v: number | null | undefined): string {
  return `¥${(v || 0).toFixed((v || 0) < 0.1 ? 3 : 2)}`;
}

// ── 节点图 ──

interface RunNodeData extends Record<string, unknown> {
  label: string;
  sub: string;
  status: StepStatus | 'pending';
  gate: boolean;
  disabled: boolean;
  round: number;
  attempt: number;
  selected: boolean;
  executor: string;
}

function RunNodeCard({ data }: NodeProps<Node<RunNodeData>>) {
  const c = STATUS_COLOR[data.status] || color.line;
  return (
    <div
      className="cw-runnode"
      data-status={data.status}
      data-gate={data.gate ? 'true' : undefined}
      data-selected={data.selected ? 'true' : undefined}
      data-disabled={data.disabled ? 'true' : undefined}
      style={{ ['--node-c' as string]: c }}
    >
      <Handle type="target" position={Position.Left} className="cw-runnode-dot" />
      <div className="cw-runnode-head">
        {data.gate ? <User size={12} aria-hidden /> : <Bot size={12} aria-hidden />}
        <span>{data.label}</span>
        {data.round > 1 ? <em className="cw-num">第 {data.round} 轮</em> : null}
      </div>
      <div className="cw-runnode-body">
        <span className="cw-runnode-st">{data.disabled ? '已关闭' : STATUS_LABEL[data.status]}</span>
        <span className="cw-muted">{data.sub}</span>
        {data.attempt > 1 ? <span className="cw-muted cw-num">尝试 {data.attempt}</span> : null}
      </div>
      {data.status === 'waiting' ? <span className="cw-runnode-cta">去处理</span> : null}
      <Handle type="source" position={Position.Right} className="cw-runnode-dot" />
    </div>
  );
}

const NODE_TYPES = { run: RunNodeCard };

/** 连线标注传递的产物（按上游角色） */
const EDGE_LABEL: Record<string, string> = {
  researcher: '研究简报',
  aggregator: '研究简报',
  planner: '方向卡',
  writer: '文稿',
  reviewer: '审校意见',
  storyboarder: '分镜',
  artist: '关键帧',
  producer: '成片',
  qa: '质检报告',
};

/** 按拓扑深度分列；并行节点每个分支一个卡片竖向排开。返回 [节点, 边]。 */
export function layoutRunGraph(
  graph: FlowGraph,
  steps: StepView[],
  inputs: Record<string, unknown>,
  selected: string | null,
): [Node<RunNodeData>[], Edge[]] {
  const depth = new Map<string, number>();
  for (const n of graph.nodes) {
    const preds = graph.edges.filter((e) => e.to === n.id && !e.loop).map((e) => depth.get(e.from) ?? 0);
    depth.set(n.id, preds.length ? Math.max(...preds) + 1 : 0);
  }
  const rendered = new Map<string, string[]>();
  const nodes: Node<RunNodeData>[] = [];
  for (const n of graph.nodes) {
    const all = nodeSteps(steps, n.id);
    let branches: (string | null)[] = [null];
    if (n.parallel) {
      const fromInputs = ((inputs[n.parallel] as string[]) || []).map(String);
      const fromSteps = all.map((s) => s.branch || '').filter(Boolean);
      branches = [...new Set([...fromInputs, ...fromSteps])];
      if (!branches.length) branches = [null];
    }
    const ids: string[] = [];
    branches.forEach((b, i) => {
      const mine = b == null ? all : all.filter((s) => (s.branch || '') === b);
      const last = mine[mine.length - 1];
      const id = b == null ? n.id : `${n.id}:${b}`;
      ids.push(id);
      const y = (i - (branches.length - 1) / 2) * 96;
      nodes.push({
        id,
        type: 'run',
        position: { x: (depth.get(n.id) || 0) * 280, y },
        draggable: false,
        data: {
          label: b ? `${n.label} · ${BRANCH_LABEL[b] || b}` : n.label,
          sub: n.type === 'gate' ? '人工关卡' : EXECUTOR_LABEL[last?.executor || n.executor] || last?.executor || n.executor,
          status: nodeStatus(mine),
          gate: n.type === 'gate',
          disabled: n.type === 'gate' && !n.enabled,
          round: last?.round || 1,
          attempt: Math.max(1, ...mine.map((s) => s.attempt)),
          selected: selected === id,
          executor: last?.executor || n.executor,
        },
      });
    });
    rendered.set(n.id, ids);
  }
  const edges: Edge[] = [];
  for (const e of graph.edges) {
    const fromNode = graph.nodes.find((n) => n.id === e.from);
    const label = e.loop ? `退回（最多 ${e.max_loops ?? 1} 次）` : EDGE_LABEL[fromNode?.role || ''] ?? '';
    for (const s of rendered.get(e.from) || []) {
      for (const t of rendered.get(e.to) || []) {
        const done = nodes.find((n) => n.id === s)?.data.status;
        edges.push({
          id: `${s}->${t}`,
          source: s,
          target: t,
          label: (rendered.get(e.from) || []).length > 1 ? undefined : label,
          animated: done === 'running',
          type: e.loop ? 'smoothstep' : undefined,
          style: e.loop
            ? { stroke: color.yl, strokeWidth: 1.2, strokeDasharray: '4 4' }
            : { stroke: done === 'done' || done === 'reused' ? color.dim : color.line, strokeWidth: 1.5 },
          labelStyle: { fill: color.dim, fontSize: 11 },
          labelBgStyle: { fill: color.base },
        });
      }
    }
  }
  return [nodes, edges];
}

export function RunGraph({
  detail,
  selected,
  onSelect,
}: {
  detail: RunDetail;
  selected: string | null;
  onSelect: (renderId: string) => void;
}) {
  const [nodes, edges] = useMemo(
    () => layoutRunGraph(detail.graph, detail.steps, detail.run.inputs, selected),
    [detail.graph, detail.steps, detail.run.inputs, selected],
  );
  return (
    <div className="cw-rungraph" role="figure" aria-label="运行节点图">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={NODE_TYPES}
        fitView
        fitViewOptions={{ padding: 0.2, minZoom: 0.7 }}
        nodesConnectable={false}
        proOptions={{ hideAttribution: true }}
        onNodeClick={(_, n) => onSelect(n.id)}
        minZoom={0.4}
        maxZoom={1.6}
      >
        <Background color={color.grat} gap={24} />
      </ReactFlow>
    </div>
  );
}

/** 节点图上的渲染 id（node 或 node:branch）→ 最新步骤 */
export function stepForRenderId(steps: StepView[], rid: string | null): StepView | null {
  if (!rid) return null;
  const [node, branch] = rid.split(':');
  const mine = steps.filter((s) => s.node === node && (branch ? s.branch === branch : true));
  return mine[mine.length - 1] || null;
}

// ── 时间线 ──

export function RunTimeline({ steps, now, onSelect }: { steps: StepView[]; now: number; onSelect: (s: StepView) => void }) {
  const spans = steps.map((s) => {
    const a = new Date(s.started_at).getTime();
    const b = s.finished_at ? new Date(s.finished_at).getTime() : now;
    return { s, a, b: Math.max(b, a + 300) };
  });
  if (!spans.length) return <p className="cw-muted">还没有步骤</p>;
  const t0 = Math.min(...spans.map((x) => x.a));
  const t1 = Math.max(...spans.map((x) => x.b));
  const total = Math.max(t1 - t0, 1000);
  return (
    <div className="cw-runtl">
      <div className="cw-runtl-axis cw-num cw-muted">
        <span>0s</span>
        <span>{fmtMs(total / 2)}</span>
        <span>{fmtMs(total)}</span>
      </div>
      {spans.map(({ s, a, b }) => (
        <button key={s.id} type="button" className="cw-runtl-row" onClick={() => onSelect(s)}>
          <span className="cw-runtl-name">
            {s.label}
            {s.branch ? ` · ${BRANCH_LABEL[s.branch] || s.branch}` : ''}
            {s.attempt > 1 ? <em className="cw-muted"> 重试 {s.attempt - 1}</em> : null}
          </span>
          <span className="cw-runtl-track">
            <span
              className="cw-runtl-bar"
              data-human={s.executor === 'human' ? 'true' : undefined}
              title={`${STATUS_LABEL[s.status]} · ${fmtMs(s.duration_ms ?? b - a)}`}
              style={{
                left: `${((a - t0) / total) * 100}%`,
                width: `${Math.max(((b - a) / total) * 100, 0.8)}%`,
                background: STATUS_COLOR[s.status],
              }}
            />
          </span>
          <span className="cw-num cw-muted cw-runtl-dur">{s.executor === 'human' ? `等待 ${fmtMs(s.duration_ms ?? b - a)}` : fmtMs(s.duration_ms ?? b - a)}</span>
        </button>
      ))}
    </div>
  );
}

// ── 调用树 ──

const KIND_LABEL: Record<string, string> = { llm: '模型调用', tool: '工具调用', agent_event: '外部 agent' };

function PayloadView({ spanId }: { spanId: string }) {
  const [data, setData] = useState<Record<string, unknown> | null | undefined>(undefined);
  useEffect(() => {
    runsApi
      .payload(spanId)
      .then(setData)
      .catch(() => setData(null));
  }, [spanId]);
  if (data === undefined) return <p className="cw-muted">加载载荷…</p>;
  if (data === null) return <p className="cw-muted">没有载荷（可能已清理）</p>;
  return <pre className="cw-payload">{JSON.stringify(data, null, 2)}</pre>;
}

function SpanRow({ sp }: { sp: SpanView }) {
  const [open, setOpen] = useState(false);
  const Icon = sp.kind === 'tool' ? Wrench : Bot;
  return (
    <li className="cw-trace-span" data-error={sp.status === 'error' ? 'true' : undefined}>
      <button type="button" className="cw-trace-line" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
        {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        <Icon size={12} aria-hidden />
        <span className="cw-trace-kind">{KIND_LABEL[sp.kind] || sp.kind}</span>
        <span className="cw-trace-name">{sp.name}</span>
        <span className="cw-muted cw-trace-sum">{sp.error || sp.summary}</span>
        <span className="cw-num cw-muted">{fmtMs(sp.duration_ms)}</span>
        <span className="cw-num cw-muted">{sp.kind === 'llm' ? fmtCost(sp.cost) : ''}</span>
      </button>
      {open ? (
        <div className="cw-trace-body">
          {Object.keys(sp.attributes || {}).length ? (
            <dl className="cw-kv">
              {Object.entries(sp.attributes).map(([k, v]) => (
                <div key={k}>
                  <dt>{k}</dt>
                  <dd>{typeof v === 'object' ? JSON.stringify(v) : String(v ?? '')}</dd>
                </div>
              ))}
            </dl>
          ) : null}
          {sp.has_payload ? <PayloadView spanId={sp.id} /> : null}
        </div>
      ) : null}
    </li>
  );
}

export function TraceTree({ items }: { items: TraceStep[] }) {
  const [kind, setKind] = useState<'all' | 'llm' | 'tool' | 'error'>('all');
  const [open, setOpen] = useState<Set<number>>(new Set());
  const filtered = items
    .map((s) => ({
      ...s,
      children: s.children.filter((c) =>
        kind === 'all' ? true : kind === 'error' ? c.status === 'error' : c.kind === kind,
      ),
    }))
    .filter((s) => kind === 'all' || s.children.length || (kind === 'error' && s.status === 'failed'));
  return (
    <div>
      <div className="cw-seg" role="group" aria-label="按类型筛选" style={{ marginBottom: 10 }}>
        {(
          [
            ['all', '全部'],
            ['llm', '模型调用'],
            ['tool', '工具调用'],
            ['error', '只看错误'],
          ] as const
        ).map(([k, l]) => (
          <button key={k} type="button" aria-pressed={kind === k} onClick={() => setKind(k)}>
            {l}
          </button>
        ))}
      </div>
      {filtered.length === 0 ? <p className="cw-muted">没有匹配的调用</p> : null}
      <ul className="cw-trace">
        {filtered.map((s) => {
          const isOpen = open.has(s.id) || kind !== 'all';
          return (
            <li key={s.id} className="cw-trace-step">
              <button
                type="button"
                className="cw-trace-line"
                aria-expanded={isOpen}
                onClick={() =>
                  setOpen((prev) => {
                    const n = new Set(prev);
                    if (n.has(s.id)) n.delete(s.id);
                    else n.add(s.id);
                    return n;
                  })
                }
              >
                {isOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                <span className="cw-trace-dot" style={{ background: STATUS_COLOR[s.status] }} />
                <span className="cw-trace-name">
                  {s.label}
                  {s.branch ? ` · ${BRANCH_LABEL[s.branch] || s.branch}` : ''}
                </span>
                <span className="cw-muted cw-trace-sum">
                  {s.error || `${s.llm_calls} 次模型调用 · ${s.tool_calls} 次工具调用`}
                </span>
                <span className="cw-num cw-muted">{fmtMs(s.duration_ms)}</span>
                <span className="cw-num cw-muted">{fmtCost(s.cost)}</span>
              </button>
              {isOpen ? (
                <ul className="cw-trace-children">
                  {s.children.length === 0 ? <li className="cw-muted" style={{ padding: '4px 0' }}>没有调用</li> : null}
                  {s.children.map((c) => (
                    <SpanRow key={c.id} sp={c} />
                  ))}
                </ul>
              ) : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

// ── 产物 ──

function SourceLink({ s }: { s: SourceRef }) {
  if (s.type === 'content' && s.id) return <Link href={`/items/${s.id}`}>{s.title || `内容 #${s.id}`}</Link>;
  if (s.type === 'library' && s.id) return <Link href={`/library?item=${s.id}`}>{s.title || `灵感库 #${s.id}`}</Link>;
  return (
    <a href={s.url || '#'} target="_blank" rel="noreferrer">
      {s.title || s.url}
    </a>
  );
}

export function ArtifactBody({ a }: { a: ArtifactView }) {
  const c = a.content || {};
  return (
    <div className="cw-artifact">
      {c.summary ? <p>{c.summary}</p> : null}
      {c.findings?.length ? (
        <ol className="cw-findings">
          {c.findings.map((f) => (
            <li key={f.id} id={`a${a.id}-${f.id}`}>
              <span className="cw-num cw-muted">{f.id}</span> {f.claim}
              <div className="cw-finding-src">
                {f.sources.map((s, i) => (
                  <span key={i}>
                    <SourceLink s={s} />
                  </span>
                ))}
              </div>
            </li>
          ))}
        </ol>
      ) : a.kind === 'research_brief' ? (
        <p className="cw-muted">没有带出处的结论</p>
      ) : null}
      {c.cards?.length ? (
        <div className="cw-dircards">
          {c.cards.map((d) => (
            <DirectionCardView key={d.id} card={d} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function DirectionCardView({ card, picked, onPick }: { card: DirectionCard; picked?: boolean; onPick?: () => void }) {
  const body = (
    <>
      <div className="cw-dircard-head">
        <b>{card.title}</b>
        {card.format ? <span className="cw-chip">{card.format}</span> : null}
      </div>
      <p>{card.angle}</p>
      <p className="cw-muted">{card.why_now}</p>
      {card.refs.length ? <p className="cw-muted cw-num">依据 {card.refs.join(' · ')}</p> : null}
    </>
  );
  return onPick ? (
    <button type="button" className="cw-dircard" aria-pressed={picked} onClick={onPick}>
      {body}
    </button>
  ) : (
    <div className="cw-dircard">{body}</div>
  );
}

// ── 人工关卡 ──

export function GatePanel({ runId, step, onDone }: { runId: number; step: StepView; onDone: () => void }) {
  const options = (step.meta.options as DirectionCard[]) || [];
  const [pick, setPick] = useState<string | null>(null);
  const [custom, setCustom] = useState('');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    try {
      await runsApi.gate(runId, pick ? { card_id: pick, note: note || undefined } : { custom, note: note || undefined });
      message.success('已提交，流程继续');
      onDone();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '提交失败');
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="cw-gate" aria-live="polite">
      <h3 className="cw-detail-h">〔{step.label}〕选一个方向，或写下你的方向</h3>
      <div className="cw-dircards">
        {options.map((o) => (
          <DirectionCardView key={o.id} card={o} picked={pick === o.id} onPick={() => setPick(pick === o.id ? null : o.id)} />
        ))}
      </div>
      <div className="cw-gate-form">
        <Input
          placeholder="都不满意？写下你的方向"
          value={custom}
          disabled={!!pick}
          onChange={(e) => setCustom(e.target.value)}
          maxLength={500}
        />
        <Input placeholder="备注（可选）" value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} />
        <Button variant="primary" disabled={busy || (!pick && !custom.trim())} onClick={submit}>
          {busy ? '提交中…' : '确定'}
        </Button>
      </div>
    </section>
  );
}

// ── 节点详情 ──

export function StepDetailPanel({
  runId,
  stepId,
  canFork,
  canCompare = false,
  onForked,
}: {
  runId: number;
  stepId: number;
  canFork: boolean;
  canCompare?: boolean;
  onForked: (newRunId: number) => void;
}) {
  const [d, setD] = useState<StepDetailData | null>(null);
  const [showPrompt, setShowPrompt] = useState(false);
  const [forkOpen, setForkOpen] = useState(false);
  const [extra, setExtra] = useState('');
  const [group, setGroup] = useState('');
  const [executor, setExecutor] = useState('');

  useEffect(() => {
    setD(null);
    runsApi
      .step(runId, stepId)
      .then(setD)
      .catch(() => setD(null));
  }, [runId, stepId]);

  if (!d) return <p className="cw-muted">加载节点详情…</p>;
  const tools = d.children.filter((c) => c.kind === 'tool');
  const fork = async () => {
    try {
      const r = await runsApi.fork(runId, {
        node: d.node,
        prompt_extra: extra || undefined,
        routing_group: group || undefined,
        executor: executor || undefined,
      });
      setForkOpen(false);
      onForked(r.id);
    } catch (err) {
      message.error(err instanceof Error ? err.message : '重跑失败');
    }
  };
  return (
    <div className="cw-stepdetail">
      <div className="cw-stepdetail-head">
        <b>
          {d.label}
          {d.branch ? ` · ${BRANCH_LABEL[d.branch] || d.branch}` : ''}
        </b>
        <span className="cw-chip" style={{ borderColor: STATUS_COLOR[d.status], color: STATUS_COLOR[d.status] }}>
          {STATUS_LABEL[d.status]}
        </span>
        <span className="cw-muted">{EXECUTOR_LABEL[d.executor] || d.executor}</span>
        <span className="cw-grow" />
        {canCompare && d.executor !== 'human' ? (
          <Link className="cw-link-btn" href={`/runs/${runId}/compare?node=${encodeURIComponent(d.node)}`}>
            对比
          </Link>
        ) : null}
        {canFork && d.executor !== 'human' ? (
          <Button icon={<GitBranch size={14} />} onClick={() => setForkOpen(true)}>
            从这里重跑
          </Button>
        ) : null}
      </div>
      <dl className="cw-kv cw-kv-inline">
        <div>
          <dt>输入</dt>
          <dd>{d.inputs.length ? d.inputs.map((a) => `${a.title}`).join('、') : '流程输入'}</dd>
        </div>
        <div>
          <dt>模型</dt>
          <dd>{d.model || (d.meta.routing_group ? `模型组 ${String(d.meta.routing_group)}` : '—')}</dd>
        </div>
        <div>
          <dt>token</dt>
          <dd className="cw-num">
            {d.input_tokens.toLocaleString()} / {d.output_tokens.toLocaleString()}
          </dd>
        </div>
        <div>
          <dt>花费</dt>
          <dd className="cw-num">{fmtCost(d.cost)}</dd>
        </div>
        <div>
          <dt>耗时</dt>
          <dd className="cw-num">{fmtMs(d.duration_ms)}</dd>
        </div>
        <div>
          <dt>尝试</dt>
          <dd className="cw-num">{d.attempt}</dd>
        </div>
      </dl>
      {d.error ? (
        <div className="cw-step-error">
          <b>错误：</b>
          {d.error}
          <div className="cw-muted">处理建议：检查模型设置或网络后，在运行顶部点「继续」，会从这个步骤重新执行；上游步骤不会重跑。</div>
        </div>
      ) : null}
      {d.status === 'reused' ? <p className="cw-muted">这个步骤复用了父运行的产物，没有重新执行。</p> : null}
      {d.prompt?.messages ? (
        <>
          <button type="button" className="cw-link-btn" onClick={() => setShowPrompt((v) => !v)}>
            {showPrompt ? '▾' : '▸'} 提示词（第一次模型调用，渲染后）
          </button>
          {showPrompt ? (
            <div className="cw-prompt">
              {d.prompt.messages.map((m, i) => (
                <div key={i}>
                  <span className="cw-chip">{m.role}</span>
                  <pre className="cw-payload">{m.content}</pre>
                </div>
              ))}
            </div>
          ) : null}
        </>
      ) : null}
      <h4 className="cw-detail-h">工具调用（{tools.length}）</h4>
      {tools.length ? (
        <ul className="cw-trace-children">
          {tools.map((c) => (
            <SpanRow key={c.id} sp={c} />
          ))}
        </ul>
      ) : (
        <p className="cw-muted">没有工具调用</p>
      )}
      <h4 className="cw-detail-h">输出</h4>
      {d.outputs.length ? (
        d.outputs.map((a) => (
          <div key={a.id}>
            <div className="cw-muted" style={{ fontSize: 12 }}>
              {a.title}
            </div>
            <ArtifactBody a={a} />
          </div>
        ))
      ) : d.meta.summary ? (
        <p>{String(d.meta.summary)}</p>
      ) : (
        <p className="cw-muted">没有输出</p>
      )}
      <Modal
        open={forkOpen}
        title={`从「${d.label}」重跑`}
        okText="开始重跑"
        cancelText="取消"
        onOk={fork}
        onCancel={() => setForkOpen(false)}
      >
        <p className="cw-muted">会新建一个分叉运行：上游步骤直接复用这次的产物，从这个节点起按下面的设置重新执行。原运行保留。</p>
        <Input.TextArea rows={3} placeholder="给这个角色的额外要求（可选）" value={extra} onChange={(e) => setExtra(e.target.value)} />
        <Input style={{ marginTop: 8 }} placeholder="换模型组（可选，例如 quality）" value={group} onChange={(e) => setGroup(e.target.value)} />
        {d.role === 'producer' ? (
          <Select
            style={{ marginTop: 8, width: '100%' }}
            value={executor}
            onChange={setExecutor}
            aria-label="换执行者"
            options={[
              { value: '', label: '执行者不变' },
              { value: 'deepseek_harness', label: 'DeepSeek Harness' },
              { value: 'claude_code', label: 'Claude Code' },
              { value: 'codex', label: 'Codex' },
            ]}
          />
        ) : null}
      </Modal>
    </div>
  );
}
