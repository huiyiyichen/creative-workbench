import { describe, expect, it } from 'vitest';
import { artKind, artSpec, hashStr, seeded, tracePath } from './signal-art';

describe('signal-art', () => {
  it('同一标题同一张图', () => {
    expect(artSpec('Remotion 入门', 'video')).toEqual(artSpec('Remotion 入门', 'video'));
    expect(artSpec('A', 'video')).not.toEqual(artSpec('B', 'video'));
  });
  it('随机数确定且在 0–1', () => {
    const a = seeded(hashStr('x'));
    const b = seeded(hashStr('x'));
    for (let i = 0; i < 20; i += 1) {
      const v = a();
      expect(v).toBe(b());
      expect(v).toBeGreaterThan(0);
      expect(v).toBeLessThan(1);
    }
  });
  it('迹线不出画框', () => {
    const d = tracePath(123, { base: 45, amp: 60, freq: 5, noise: 40 });
    const ys = [...d.matchAll(/,(-?[\d.]+)/g)].map((m) => Number(m[1]));
    expect(Math.min(...ys)).toBeGreaterThanOrEqual(2);
    expect(Math.max(...ys)).toBeLessThanOrEqual(88);
  });
  it('形态映射', () => {
    expect(artKind('xhs')).toBe('image');
    expect(artKind('prompt_bundle')).toBe('prompt');
    expect(artKind(undefined)).toBe('other');
    expect(artSpec('t', 'video').progress).toBeGreaterThan(0);
    expect(artSpec('t', 'repo').dots.length).toBeGreaterThan(3);
  });
  it('文章封面两档：段落 2 或 5 条、同信源迹线位置固定、段落不压形态字', () => {
    const titles = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'];
    for (const t of titles) {
      const sp = artSpec(t, 'article', 'Hacker News');
      expect([2, 5]).toContain(sp.rects.length);
      expect(Math.min(...sp.rects.map((x) => x.y))).toBeGreaterThanOrEqual(26);
    }
    const base = (t: string) => Number(/M[\d.]+,([\d.]+)/.exec(artSpec(t, 'article', 'RSS').traces[0].d)![1]);
    const sides = new Set(titles.map((t) => base(t) < 45));
    expect(sides.size).toBe(1);
    expect(base('a') < 45).toBe(false);
    expect(Number(/M[\d.]+,([\d.]+)/.exec(artSpec('a', 'article', 'hackernews').traces[0].d)![1]) < 45).toBe(true);
  });
});
