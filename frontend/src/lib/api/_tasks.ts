/** 任务中心（创作工作台设计 7）：流程运行、生成、采集、分析合成的一张任务表。 */
import { BASE_URL, request } from './_core';
import { onEvent } from '../events';

export type TaskType = 'flow' | 'generation' | 'sync' | 'analysis' | 'feishu';
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

/** 任务摘要推送（全局事件流的 tasks 主题，整页共用一条连接） */
export function subscribeTasks(onPush: (p: TaskPush) => void): () => void {
  let first = true;
  return onEvent<TaskPush>('tasks', (p) => {
    // 订阅时补发的是缓存快照：不带「刚结束」，免得重复弹通知
    onPush(first ? { ...p, finished: [] } : p);
    first = false;
  });
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
  feishu: '飞书',
};

/** 抽屉分组：进行中（含等待）/ 失败 / 完成（含停止） */
export function groupTasks(items: TaskView[]): { id: 'active' | 'failed' | 'done'; label: string; items: TaskView[] }[] {
  return [
    { id: 'active' as const, label: '进行中', items: items.filter((t) => t.status === 'running' || t.status === 'waiting') },
    { id: 'failed' as const, label: '失败', items: items.filter((t) => t.status === 'failed') },
    { id: 'done' as const, label: '完成', items: items.filter((t) => t.status === 'done' || t.status === 'stopped') },
  ].filter((g) => g.items.length);
}

export type TaskEntry = { kind: 'one'; task: TaskView } | { kind: 'fold'; key: string; tasks: TaskView[] };

/**
 * 列表折叠（评审 #4 P1-1）：同类、同原因的失败 ≥3 条，或同类、同标题的完成 ≥2 条，折成一行放在第一条的位置。
 * 进行中 / 等待的任务从不折叠。
 */
export function foldTasks(items: TaskView[]): TaskEntry[] {
  const keyOf = (t: TaskView): string | null => {
    if (t.status === 'failed') return `f|${t.kind}|${t.reason || ''}`;
    if (t.status === 'done') return `d|${t.kind}|${t.title}`;
    return null;
  };
  const buckets = new Map<string, TaskView[]>();
  for (const t of items) {
    const k = keyOf(t);
    if (k) buckets.set(k, [...(buckets.get(k) || []), t]);
  }
  const folded = (k: string) => {
    const n = buckets.get(k)!.length;
    return k.startsWith('f|') ? n >= 3 : n >= 2;
  };
  const out: TaskEntry[] = [];
  const seen = new Set<string>();
  for (const t of items) {
    const k = keyOf(t);
    if (k && folded(k)) {
      if (!seen.has(k)) {
        seen.add(k);
        out.push({ kind: 'fold', key: k, tasks: buckets.get(k)! });
      }
    } else out.push({ kind: 'one', task: t });
  }
  return out;
}

export function fmtDuration(ms: number | null): string {
  if (ms === null || ms === undefined) return '—';
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s} 秒`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} 分 ${s % 60} 秒`;
  return `${Math.floor(m / 60)} 小时 ${m % 60} 分`;
}
