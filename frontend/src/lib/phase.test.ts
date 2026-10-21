import { describe, expect, it } from 'vitest';
import { DAY_X, ZERO_Y, ageX, changeRate, changeY, phasePoints } from './phase';

describe('phase', () => {
  it('刻度', () => {
    expect(ageX(0)).toBe(0);
    expect(ageX(1000)).toBe(1);
    expect(DAY_X).toBeGreaterThan(0.5);
    expect(changeY(2)).toBe(0);
    expect(changeY(-1)).toBe(1);
    expect(ZERO_Y).toBeGreaterThan(0.5);
  });
  it('变化率', () => {
    expect(changeRate(20, 10)).toBe(1);
    expect(changeRate(5, 10)).toBe(-0.5);
    expect(changeRate(3, 0)).toBeNull();
    expect(changeRate(null, 3)).toBe(0);
  });
  it('点', () => {
    const now = Date.parse('2026-10-21T00:00:00Z');
    const pts = phasePoints(
      [
        { id: 1, first_seen_at: '2026-10-20T22:00:00Z', signal: 30, signal_prev: 10, content_count: 9 },
        { id: 2, first_seen_at: null, signal: 1, signal_prev: 1, content_count: 1 },
        { id: 3, first_seen_at: '2026-10-15T00:00:00Z', signal: 2, signal_prev: 10, content_count: 1 },
      ],
      now,
    );
    expect(pts.map((p) => p.id)).toEqual([1, 3]);
    expect(pts[0].x).toBeLessThan(pts[1].x);
    expect(pts[0].y).toBeLessThan(ZERO_Y);
    expect(pts[0].x).toBeGreaterThan(0);
    expect(pts[1].y).toBeGreaterThan(ZERO_Y);
    expect(pts[0].r).toBe(10);
  });

  it('首次观测带：同一时刻的一批点向右铺开、两行错位，不叠在一起', () => {
    const now = Date.UTC(2026, 9, 21, 8);
    const first = new Date(now - 5 * 3600000).toISOString();
    const rows = Array.from({ length: 8 }, (_, i) => ({ id: i, first_seen_at: first, signal: 3, signal_prev: null, content_count: 1 }));
    const pts = phasePoints(rows, now);
    const keys = new Set(pts.map((p) => `${p.x.toFixed(4)}|${p.y.toFixed(4)}`));
    expect(keys.size).toBe(8);
    expect(new Set(pts.map((p) => p.y)).size).toBe(2);
  });
});
