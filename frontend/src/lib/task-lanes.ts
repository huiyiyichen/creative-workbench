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

export type LaneBatch = { key: string; left: number; width: number; status: TaskStatus; count: number; failed: number; clips: LaneClip[] };

/**
 * 把挨得很近（间隔小于 gap，窗口比例）的片段合成一个批次块。
 * 只有全部失败才算失败（整块红）；部分失败仍按成功画，块里按比例画一段红（failed / count），免得 1 个失败盖住 23 个成功。
 * 有失败的批次排在最后画（压在上面）。
 */
export function batchClips(clips: LaneClip[], gap = 0.006): LaneBatch[] {
  const out: LaneBatch[] = [];
  for (const c of clips) {
    const last = out[out.length - 1];
    if (last && c.left <= last.left + last.width + gap) {
      last.width = Math.max(last.width, c.left + c.width - last.left);
      last.clips.push(c);
      last.count += 1;
      if (c.status === 'failed') last.failed += 1;
      if (c.status === 'running' || c.status === 'waiting') last.status = c.status;
    } else {
      out.push({ key: c.key, left: c.left, width: c.width, status: c.status, count: 1, failed: c.status === 'failed' ? 1 : 0, clips: [c] });
    }
  }
  for (const b of out) if (b.failed && b.failed === b.count) b.status = 'failed';
  return out.sort((a, b) => Number(a.failed > 0) - Number(b.failed > 0));
}

/**
 * 任务都挤在窗口一小段时，把窗口缩到「最早任务前 30 分钟 → 现在」，最短 2 小时。
 * 返回新的起点（不缩时原样返回）。
 */
export function fitWindow(items: TaskView[], start: number, end: number): number {
  let first = Infinity;
  for (const t of items) {
    const s = new Date(t.started_at || t.created_at).getTime();
    if (s >= start && s < first) first = s;
  }
  if (!Number.isFinite(first)) return start;
  const fitted = Math.min(first - 30 * 60 * 1000, end - 2 * 3600 * 1000);
  return (end - fitted) / (end - start) < 0.4 ? Math.max(start, fitted) : start;
}
