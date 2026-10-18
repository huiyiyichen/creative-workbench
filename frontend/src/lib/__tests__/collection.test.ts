import { describe, expect, it } from 'vitest';
import { delta, hasSourceProblems, intervalLabel, relativeTime } from '@/lib/collection';
import type { SourceHealthRow } from '@/lib/api/_collection';

const row = (state: SourceHealthRow['state'], enabled = true) => ({ state, enabled }) as SourceHealthRow;

describe('collection helpers', () => {
  it('缺失值不计算变化', () => {
    expect(delta({ value: null, previous: 3 })).toBeNull();
    expect(delta({ value: 3, previous: null })).toBeNull();
    expect(delta({ value: 5, previous: 3 })).toEqual({ text: '+2', dir: 'up' });
    expect(delta({ value: 1, previous: 3 })).toEqual({ text: '−2', dir: 'down' });
    expect(delta({ value: 2, previous: 1 }, false)).toEqual({ text: '+1', dir: 'down' });
    expect(delta({ value: 2, previous: 2 })).toEqual({ text: '持平', dir: 'flat' });
  });

  it('只把暂停 / 失败 / 可能失效的启用信源算作需要处理', () => {
    expect(hasSourceProblems([row('ok'), row('empty')])).toBe(false);
    expect(hasSourceProblems([row('error', false)])).toBe(false);
    expect(hasSourceProblems([row('ok'), row('stale')])).toBe(true);
  });

  it('相对时间', () => {
    const now = new Date('2026-10-18T12:00:00Z');
    expect(relativeTime(null, now)).toBe('—');
    expect(relativeTime('2026-10-18T11:57:00Z', now)).toBe('3 分钟前');
    expect(relativeTime('2026-10-18T14:00:00Z', now)).toBe('2 小时后');
    expect(relativeTime('2026-10-15T12:00:00Z', now)).toBe('3 天前');
  });

  it('间隔文字', () => {
    expect(intervalLabel(30)).toBe('30 分钟');
    expect(intervalLabel(120)).toBe('2 小时');
    expect(intervalLabel(1440)).toBe('1 天');
  });
});
