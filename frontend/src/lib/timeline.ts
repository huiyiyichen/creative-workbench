/** 时间线的视图窗口与片段聚合（纯函数）。 */

import type { SignalClip } from './api/_discover';
import { dayPosition, type SignalRange } from './discover';

const H = 3600 * 1000;

export type TimelineView = { start: string; end: string; startMs: number; endMs: number; zoomed: boolean };

/**
 * 「今天」视图在一天还早时自动缩放到 [00:00, max(现在 + 3h, 09:00)]，免得 87% 都是空白的未来。
 * 其他范围原样返回。
 */
export function timelineView(range: SignalRange, start: string, end: string, now: string): TimelineView {
  const s = new Date(start).getTime();
  const e = new Date(end).getTime();
  const n = new Date(now).getTime();
  if (range === 'today' && e > s) {
    const want = Math.max(n + 3 * H, s + 9 * H);
    const ve = Math.min(e, Math.ceil((want - s) / H) * H + s);
    if (ve < e) return { start, end: new Date(ve).toISOString(), startMs: s, endMs: ve, zoomed: true };
  }
  return { start, end, startMs: s, endMs: e, zoomed: false };
}

export type ClipGroup = { pos: number; span: number; items: SignalClip[] };

/**
 * 相邻片段间距小于 gap（窗口比例，默认 0.6%）时串成一组；组里超过 3 条时界面画成密度柱。
 * 输入顺序无关，输出按时间排序。
 */
export function clusterClips(items: SignalClip[], start: string, end: string, gap = 0.006): ClipGroup[] {
  const sorted = [...items].sort((a, b) => new Date(a.at).getTime() - new Date(b.at).getTime());
  const out: ClipGroup[] = [];
  let cur: ClipGroup | null = null;
  let last = -1;
  for (const c of sorted) {
    const p = dayPosition(c.at, start, end);
    if (cur && p - last <= gap) {
      cur.items.push(c);
      cur.span = p - cur.pos;
    } else {
      cur = { pos: p, span: 0, items: [c] };
      out.push(cur);
    }
    last = p;
  }
  return out;
}
