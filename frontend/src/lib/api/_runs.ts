/** 流程运行（改造方案 2.2 / 2.3）：运行、步骤、调用树、产物与溯源、工作台工具令牌。 */
import { BASE_URL, request } from './_core';

export type RunStatus = 'queued' | 'running' | 'waiting' | 'paused' | 'done' | 'failed' | 'stopped';
export type StepStatus = 'running' | 'done' | 'failed' | 'waiting' | 'reused' | 'stopped';

export interface FlowGraphNode {
  id: string;
  label: string;
  type: 'role' | 'gate';
  role: string | null;
  executor: string;
  parallel: string | null;
  routing_group: string;
  enabled: boolean;
  can_disable: boolean;
}

export interface FlowGraph {
  key: string;
  name: string;
  version: number;
  nodes: FlowGraphNode[];
  edges: { from: string; to: string; loop?: boolean; max_loops?: number }[];
}

export interface FlowInputMeta {
  type: string;
  label?: string;
  required?: boolean;
  default?: unknown;
  options?: string[];
}

export interface FlowCatalogItem {
  key: string;
  name: string;
  version: number;
  description: string;
  inputs: Record<string, FlowInputMeta>;
  budget: { cost?: number; seconds?: number; steps?: number };
  graph: FlowGraph;
}

export interface RunView {
  id: number;
  flow_key: string;
  flow_version: number;
  title: string;
  project_id: number | null;
  trigger: string;
  status: RunStatus;
  status_reason: string | null;
  inputs: Record<string, unknown>;
  budget: { cost?: number; seconds?: number; steps?: number };
  outputs: Record<string, unknown> | null;
  cost: number;
  input_tokens: number;
  output_tokens: number;
  parent_run_id: number | null;
  fork_node: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  step_count?: number;
}

export interface StepView {
  id: number;
  run_id: number;
  node: string;
  branch: string | null;
  role: string;
  label: string;
  executor: string;
  status: StepStatus;
  attempt: number;
  round: number;
  input_artifact_ids: number[];
  output_artifact_ids: number[];
  model: string | null;
  input_tokens: number;
  output_tokens: number;
  cost: number;
  started_at: string;
  finished_at: string | null;
  duration_ms: number | null;
  error: string | null;
  meta: Record<string, unknown> & { summary?: string; options?: DirectionCard[]; choice?: Record<string, unknown> };
}

export interface SourceRef {
  type: 'content' | 'library' | 'url';
  id?: number;
  url?: string | null;
  title?: string | null;
}

export interface Finding {
  id: string;
  claim: string;
  sources: SourceRef[];
  refs?: string[];
}

export interface DirectionCard {
  id: string;
  title: string;
  angle: string;
  why_now: string;
  format: string | null;
  refs: string[];
  artifact_id?: number;
}

export interface ArtifactView {
  id: number;
  kind: string;
  version: number;
  title: string;
  content: (Record<string, unknown> & { summary?: string; findings?: Finding[]; cards?: DirectionCard[]; branch_label?: string }) | null;
  run_id: number | null;
  step_id: number | null;
  project_id: number | null;
  created_at: string;
  links: {
    relation: string;
    target_type: string;
    target_id: number | null;
    target_url: string | null;
    anchor: string | null;
    target_anchor: string | null;
  }[];
}

export interface SpanView {
  id: string;
  kind: 'llm' | 'tool' | 'agent_event';
  name: string;
  status: 'ok' | 'error';
  step_id: number | null;
  parent_id: string | null;
  started_at: string;
  ended_at: string | null;
  duration_ms: number | null;
  attributes: Record<string, unknown>;
  summary: string | null;
  error: string | null;
  has_payload: boolean;
  via: string;
  cost: number;
}

export interface TraceStep extends StepView {
  children: SpanView[];
  tool_calls: number;
  llm_calls: number;
}

export interface StepDetail extends TraceStep {
  inputs: ArtifactView[];
  outputs: ArtifactView[];
  prompt: { messages?: { role: string; content: string }[]; response?: unknown } | null;
}

export interface RunDetail {
  run: RunView;
  graph: FlowGraph;
  steps: StepView[];
  artifacts: ArtifactView[];
  decisions: { id: number; gate: string; step_id: number | null; options: unknown; choice: Record<string, unknown> | null; note: string | null; decided_at: string }[];
  forks: { id: number; title: string; status: RunStatus; fork_node: string | null }[];
}

export interface LineageNode {
  relation: string;
  type: string;
  id: number | null;
  url: string | null;
  anchor: string | null;
  target_anchor: string | null;
  title?: string;
  kind?: string;
  version?: number;
  platform?: string | null;
  run_id?: number | null;
  sources?: LineageNode[];
}

export interface LineageView {
  artifact: ArtifactView;
  anchor?: string | null;
  sources: LineageNode[];
  used_by: { id: number; kind: string; title: string; version: number }[];
}

export interface LineageQuery {
  target: 'paragraph' | 'version' | 'shot' | 'video' | 'platform';
  project_id?: number;
  version?: number;
  anchor?: string;
  output_id?: number;
  studio_artifact_id?: number;
  shot?: number;
}

export interface WorkbenchTool {
  name: string;
  title: string;
  description: string;
  writes: boolean;
}

export interface WorkbenchToken {
  id: number;
  label: string;
  tools: string[] | null;
  run_id: number | null;
  expires_at: string | null;
  revoked_at: string | null;
  last_used_at: string | null;
  created_at: string;
  token?: string;
}

export const runsApi = {
  flows(): Promise<{ items: FlowCatalogItem[] }> {
    return request('/flows');
  },
  list(params: { status?: string; flow_key?: string } = {}): Promise<{ items: RunView[] }> {
    const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v) as [string, string][]).toString();
    return request(`/runs${q ? `?${q}` : ''}`);
  },
  start(body: { flow_key: string; inputs: Record<string, unknown>; gates?: Record<string, boolean>; budget?: Record<string, number> }): Promise<RunView> {
    return request('/runs', { method: 'POST', body: JSON.stringify(body) });
  },
  get(id: number): Promise<RunDetail> {
    return request(`/runs/${id}`);
  },
  trace(id: number): Promise<{ items: TraceStep[] }> {
    return request(`/runs/${id}/trace`);
  },
  step(runId: number, stepId: number): Promise<StepDetail> {
    return request(`/runs/${runId}/steps/${stepId}`);
  },
  payload(spanId: string): Promise<Record<string, unknown>> {
    return request(`/runs/spans/${spanId}/payload`);
  },
  gate(id: number, body: { card_id?: string; custom?: string; note?: string }): Promise<RunView> {
    return request(`/runs/${id}/gate`, { method: 'POST', body: JSON.stringify(body) });
  },
  continue(id: number, body: { cost?: number; steps?: number; seconds?: number } = {}): Promise<RunView> {
    return request(`/runs/${id}/continue`, { method: 'POST', body: JSON.stringify(body) });
  },
  stop(id: number): Promise<RunView> {
    return request(`/runs/${id}/stop`, { method: 'POST' });
  },
  fork(id: number, body: { node: string; prompt_extra?: string; routing_group?: string; executor?: string }): Promise<RunView> {
    return request(`/runs/${id}/fork`, { method: 'POST', body: JSON.stringify(body) });
  },
  lineage(artifactId: number, anchor?: string): Promise<LineageView> {
    return request(`/artifacts/${artifactId}/lineage${anchor ? `?anchor=${encodeURIComponent(anchor)}` : ''}`);
  },
  /** 界面溯源入口：段落 / 版本 / 分镜 / 成片 / 平台稿 */
  resolveLineage(params: LineageQuery): Promise<LineageView> {
    const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v != null && v !== '').map(([k, v]) => [k, String(v)])).toString();
    return request(`/lineage?${q}`);
  },
  exportUrl(id: number, format: 'json' | 'md'): string {
    return `${BASE_URL}/runs/${id}/export?format=${format}`;
  },
  streamUrl(id: number): string {
    return `${BASE_URL}/runs/${id}/stream`;
  },
  tools(): Promise<{ items: WorkbenchTool[]; mcp_path: string }> {
    return request('/workbench/tools');
  },
  tokens(): Promise<{ items: WorkbenchToken[] }> {
    return request('/workbench/tokens');
  },
  createToken(body: { label: string; tools?: string[] | null; ttl_hours?: number | null }): Promise<WorkbenchToken> {
    return request('/workbench/tokens', { method: 'POST', body: JSON.stringify(body) });
  },
  revokeToken(id: number): Promise<{ revoked: boolean }> {
    return request(`/workbench/tokens/${id}`, { method: 'DELETE' });
  },
};

/** 运行事件流：快照 + 步骤 / 调用 / 状态事件；EventSource 断线会自动重连并重新收到快照。 */
export function subscribeRun(
  id: number,
  handlers: { snapshot?: (d: RunDetail) => void; run?: (r: RunView) => void; step?: (s: StepView) => void; span?: (s: SpanView) => void },
): () => void {
  if (typeof EventSource === 'undefined') return () => {};
  const es = new EventSource(runsApi.streamUrl(id), { withCredentials: true });
  es.addEventListener('snapshot', (e) => handlers.snapshot?.(JSON.parse((e as MessageEvent).data)));
  es.addEventListener('run', (e) => handlers.run?.(JSON.parse((e as MessageEvent).data).run));
  es.addEventListener('step', (e) => handlers.step?.(JSON.parse((e as MessageEvent).data).step));
  es.addEventListener('span', (e) => handlers.span?.(JSON.parse((e as MessageEvent).data).span));
  return () => es.close();
}

/** 运行中的步骤合并：同 id 覆盖，新步骤追加 */
export function mergeStep(steps: StepView[], s: StepView): StepView[] {
  const i = steps.findIndex((x) => x.id === s.id);
  if (i < 0) return [...steps, s];
  const next = steps.slice();
  next[i] = s;
  return next;
}

/** 节点图上每个模板节点的汇总：取该节点最新一轮的分支步骤 */
export function nodeSteps(steps: StepView[], nodeId: string): StepView[] {
  const mine = steps.filter((s) => s.node === nodeId);
  const latest = new Map<string, StepView>();
  for (const s of mine) latest.set(s.branch || '', s);
  return [...latest.values()];
}

export function nodeStatus(steps: StepView[]): StepStatus | 'pending' {
  if (!steps.length) return 'pending';
  const order: StepStatus[] = ['failed', 'waiting', 'running', 'stopped', 'done', 'reused'];
  for (const st of order) if (steps.some((s) => s.status === st)) return st;
  return 'done';
}
