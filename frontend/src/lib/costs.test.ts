import { describe, expect, it } from 'vitest';
import { groupColor, stackDays, vsAvg, yuan } from './costs';

describe('costs', () => {
  it('金额格式', () => {
    expect(yuan(0)).toBe('¥0');
    expect(yuan(0.01234)).toBe('¥0.012');
    expect(yuan(3.456)).toBe('¥3.46');
    expect(yuan(1234.5)).toBe('¥1,235');
    expect(yuan(null)).toBe('—');
  });
  it('堆叠柱从下往上、按最大值归一', () => {
    const out = stackDays(
      [
        { date: '2026-10-20', total: 2, analysis: 1, gen_image: 1 },
        { date: '2026-10-21', total: 1, analysis: 1 },
        { date: '2026-10-22', total: 0 },
      ],
      100,
    );
    expect(out[0].segs).toEqual([
      { key: 'analysis', y: 50, h: 50 },
      { key: 'gen_image', y: 0, h: 50 },
    ]);
    expect(out[1].segs[0].h).toBe(50);
    expect(out[2].segs).toEqual([]);
    expect(stackDays([{ date: 'x', total: 0 }], 10)[0].segs).toEqual([]);
  });
  it('与均值比较', () => {
    expect(vsAvg(2, 1)).toEqual({ text: '+100%', up: true });
    expect(vsAvg(0.5, 1)).toEqual({ text: '-50%', up: false });
    expect(vsAvg(1, null)).toBeNull();
    expect(groupColor('nope')).toBe('var(--cw-dim)');
  });
});
