import { describe, expect, it } from 'vitest';
import { bucketByDay, compactNum, fromLocalInput, toLocalInput, weekDays } from './publishing';

describe('publishing', () => {
  it('北京时间的周一起算', () => {
    // 2026-10-21 03:00 北京 = 周三
    const days = weekDays(new Date('2026-10-20T19:00:00Z'));
    expect(new Date(days[0]).toISOString()).toBe('2026-10-18T16:00:00.000Z'); // 10-19 周一 00:00 北京
    expect(days.length).toBe(7);
    const next = weekDays(new Date('2026-10-20T19:00:00Z'), 1);
    expect(next[0] - days[0]).toBe(7 * 86400000);
  });
  it('按天分桶', () => {
    const days = weekDays(new Date('2026-10-20T19:00:00Z'));
    const b = bucketByDay([{ at: '2026-10-19T00:30:00+08:00' }, { at: '2026-10-25T23:59:00+08:00' }, { at: '2026-10-26T00:00:00+08:00' }, { at: null }], days);
    expect(b[0].length).toBe(1);
    expect(b[6].length).toBe(1);
    expect(b.flat().length).toBe(2);
  });
  it('数字缩写与输入框转换', () => {
    expect(compactNum(1234)).toBe('1234');
    expect(compactNum(12345)).toBe('1.2 万');
    expect(compactNum(120000000)).toBe('1.2 亿');
    expect(compactNum(null)).toBe('—');
    expect(toLocalInput('2026-10-21T12:00:00Z')).toBe('2026-10-21T20:00');
    expect(fromLocalInput('2026-10-21T20:00')).toBe('2026-10-21T12:00:00.000Z');
    expect(fromLocalInput('')).toBeNull();
  });
});
