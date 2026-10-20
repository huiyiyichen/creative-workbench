import { describe, expect, it } from 'vitest';
import { cnParts, fmtDay, fmtHM } from './time-cn';
import { rulerTicks } from './discover';

describe('time-cn', () => {
  it('按北京时间显示，与浏览器时区无关', () => {
    // 2026-10-20T19:08Z = 北京 10-21 03:08 周三
    expect(fmtHM('2026-10-20T19:08:00Z')).toBe('03:08');
    expect(fmtDay('2026-10-20T19:08:00Z')).toBe('10 月 21 日 周三');
    expect(cnParts('2026-10-20T16:00:00Z').h).toBe(0);
  });
  it('今天窗口刻度从 00:00 起，每 3 小时', () => {
    const ticks = rulerTicks('today', '2026-10-21T00:00:00+08:00', '2026-10-22T00:00:00+08:00');
    expect(ticks[0]).toEqual({ pos: 0, label: '00:00' });
    expect(ticks.map((t) => t.label).slice(0, 3)).toEqual(['00:00', '03:00', '06:00']);
    expect(ticks.length).toBe(9);
  });
  it('48 小时窗口零点写日期', () => {
    const ticks = rulerTicks('48h', '2026-10-19T03:00:00+08:00', '2026-10-21T03:00:00+08:00');
    expect(ticks.some((t) => t.label === '10/20')).toBe(true);
    expect(ticks[0].label).toBe('06:00');
  });
});
