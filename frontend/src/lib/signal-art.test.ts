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
});
