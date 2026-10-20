/** 任务中心（创作工作台设计 7）：流程运行、生成、采集、分析合成的一张任务表。 */
import { BASE_URL, request } from './_core';

export type TaskType = 'flow' | 'generation' | 'sync' | 'analysis';
export type TaskStatus = 'running' | 'waiting' | 'failed' | 'done' | 'stopped';

export interface TaskView {
  key: string;
  type: TaskType;
  kind: string;
  kind_label: string;
  title: string;
  project_id: number | null;
  project_title: string | null;
  output_title: string | null;
  status: TaskStatus;
  raw_status: string;
  stage: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  cost: number;
  reason: string | null;
  hint: string | null;
  href: string;
  can_stop: boolean;
  can_retry: boolean;
}

export type TaskCounts = Record<TaskStatus, number>;

export interface TaskList {
  items: TaskView[];
  counts: TaskCounts;
  active: number;
}

export interface TaskPush {
  active: number;
  counts: TaskCounts;
  items: TaskView[];
  finished: TaskView[];
}

export const tasksApi = {
  list(params: { type?: TaskType[]; status?: TaskStatus; project?: number; days?: number; limit?: number } = {}): Promise<TaskList> {
    const sp = new URLSearchParams();
    for (const t of params.type || []) sp.append('type', t);
    if (params.status) sp.set('status', params.status);
    if (params.project) sp.set('project', String(params.project));
    if (params.days) sp.set('days', String(params.days));
    if (params.limit) sp.set('limit', String(params.limit));
    const q = sp.toString();
    return request(`/tasks${q ? `?${q}` : ''}`);
  },
  summary(): Promise<{ active: number; counts: TaskCounts; items: TaskView[] }> {
    return request('/tasks/summary');
  },
  retry(key: string): Promise<{ run_id: number }> {
    return request(`/tasks/${encodeURIComponent(key)}/retry`, { method: 'POST' });
  },
  stop(key: string): Promise<{ run_id: number; status: string }> {
    return request(`/tasks/${encodeURIComponent(key)}/stop`, { method: 'POST' });
  },
  streamUrl(): string {
    return `${BASE_URL}/tasks/stream`;
  },
};

export function subscribeTasks(onPush: (p: TaskPush) => void): () => void {
  if (typeof EventSource === 'undefined') return () => {};
  const es = new EventSource(tasksApi.streamUrl(), { withCredentials: true });
  es.addEventListener('tasks', (e) => onPush(JSON.parse((e as MessageEvent).data)));
  return () => es.close();
}

export const TASK_STATUS_LABEL: Record<TaskStatus, string> = {
  running: '进行中',
  waiting: '等你处理',
  failed: '失败',
  done: '完成',
  stopped: '已停止',
};

export const TASK_TYPE_LABEL: Record<TaskType, string> = {
  flow: '流程',
  generation: '生成',
  sync: '采集',
  analysis: '分析',
};

/** 抽屉分组：进行中（含等待）/ 失败 / 完成（含停止） */
export function groupTasks(items: TaskView[]): { id: 'active' | 'failed' | 'done'; label: string; items: TaskView[] }[] {
  return [
    { id: 'active' as const, label: '进行中', items: items.filter((t) => t.status === 'running' || t.status === 'waiting') },
    { id: 'failed' as const, label: '失败', items: items.filter((t) => t.status === 'failed') },
    { id: 'done' as const, label: '完成', items: items.filter((t) => t.status === 'done' || t.status === 'stopped') },
  ].filter((g) => g.items.length);
}

export function fmtDuration(ms: number | null): string {
  if (ms === null || ms === undefined) return '—';
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s} 秒`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} 分 ${s % 60} 秒`;
  return `${Math.floor(m / 60)} 小时 ${m % 60} 分`;
}
