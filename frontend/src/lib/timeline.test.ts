import { describe, expect, it } from 'vitest';
import { clusterClips, timelineView } from './timeline';

const S = '2026-10-21T00:00:00+08:00';
const E = '2026-10-22T00:00:00+08:00';
const clip = (id: number, hm: string) => ({ id, title: `t${id}`, at: `2026-10-21T${hm}:00+08:00`, media_type: 'article', heat: null }) as never;

describe('timeline', () => {
  it('清早缩放到 09:00，下午不缩放', () => {
    const v = timelineView('today', S, E, '2026-10-21T03:10:00+08:00');
    expect(v.zoomed).toBe(true);
    expect(new Date(v.end).getTime() - new Date(S).getTime()).toBe(9 * 3600e3);
    const v2 = timelineView('today', S, E, '2026-10-21T15:00:00+08:00');
    expect(v2.zoomed).toBe(true);
    expect(new Date(v2.end).getTime() - new Date(S).getTime()).toBe(18 * 3600e3);
    expect(timelineView('today', S, E, '2026-10-21T22:00:00+08:00').zoomed).toBe(false);
    expect(timelineView('48h', S, E, '2026-10-21T03:00:00+08:00').zoomed).toBe(false);
  });
  it('密集片段聚成一组', () => {
    const g = clusterClips([clip(1, '01:00'), clip(2, '01:01'), clip(3, '01:02'), clip(4, '01:03'), clip(5, '12:00')], S, E);
    expect(g.length).toBe(2);
    expect(g[0].items.length).toBe(4);
    expect(g[1].items[0].id).toBe(5);
  });
});
