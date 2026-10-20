/** 任务泳道（渲染队列视图）：按类型分轨，片段宽度 = 实际耗时，颜色 = 状态。 */

import type { TaskStatus, TaskType, TaskView } from './api/_tasks';

export const LANE_ORDER: TaskType[] = ['sync', 'analysis', 'flow', 'generation', 'feishu'];

export type LaneClip = { key: string; left: number; width: number; status: TaskStatus; title: string; task: TaskView };

/** 把任务放进 [start, end] 窗口；运行中的任务结束于 now。窗口外的不画，越界部分截掉。 */
export function laneClips(items: TaskView[], start: number, end: number, now: number): Map<TaskType, LaneClip[]> {
  const out = new Map<TaskType, LaneClip[]>();
  const span = end - start;
  if (span <= 0) return out;
  for (const t of items) {
    const s = new Date(t.started_at || t.created_at).getTime();
    const e = t.finished_at ? new Date(t.finished_at).getTime() : t.status === 'running' || t.status === 'waiting' ? now : s + (t.duration_ms || 0);
    if (e < start || s > end) continue;
    const a = Math.max(start, s);
    const b = Math.min(end, Math.max(e, a));
    const lane = out.get(t.type) ?? [];
    lane.push({ key: t.key, left: (a - start) / span, width: (b - a) / span, status: t.status, title: t.title, task: t });
    out.set(t.type, lane);
  }
  for (const lane of out.values()) lane.sort((x, y) => x.left - y.left);
  return out;
}

/** 失败的排最前，其次进行中 / 等你处理，再按开始时间倒序。 */
export function sortTasks(items: TaskView[]): TaskView[] {
  const rank: Record<TaskStatus, number> = { failed: 0, running: 1, waiting: 1, done: 2, stopped: 3 };
  return [...items].sort((a, b) => rank[a.status] - rank[b.status] || (b.started_at || b.created_at).localeCompare(a.started_at || a.created_at));
}
