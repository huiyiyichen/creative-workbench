import { describe, expect, it } from 'vitest';
import { buildPersonaSvg, esc, monthLabel, shareText, wrap } from './persona-card';
import type { CreatorPersona } from './api/_digests';

const p: CreatorPersona = {
  month: '2026-10',
  archetype: { key: 'night', name: '深夜写字人', tagline: '70% 的动作发生在晚上十点以后，灵感都是夜里来的' },
  stats: { actions: 30, projects: 3, outputs: 6, published: 1, library: 12, breakdowns: 2, notes: 1, revisions: 8, days: 9, streak: 4, night_pct: 70, platforms: 3, videos: 1, xhs: 2, longform: 0 },
  hours: Array.from({ length: 24 }, (_, i) => (i === 23 ? 9 : i % 3)),
  peak_hour: 23,
  platform_mix: [{ kind: 'xhs', label: '小红书', count: 2 }],
  titles: ['a'],
};

describe('persona card', () => {
  it('SVG 含人格名、数字和投票口令，并转义', () => {
    const svg = buildPersonaSvg(p, { vote: '<搜 创意工作台>' });
    expect(svg.startsWith('<svg')).toBe(true);
    expect(svg).toContain('深夜写字人');
    expect(svg).toContain('高峰 23:00');
    expect(svg).toContain('&lt;搜 创意工作台&gt;');
    expect(svg).not.toContain('<搜');
  });
  it('折行与月份', () => {
    expect(wrap('一二三四五', 2)).toEqual(['一二', '三四', '五']);
    expect(wrap('一二三四五六七', 2, 2)).toEqual(['一二', '三…']);
    expect(wrap('abcd', 2)).toEqual(['abc', 'd']);
    expect(monthLabel('2026-03')).toBe('2026 年 3 月');
    expect(esc('"&')).toBe('&quot;&amp;');
  });
  it('分享文案', () => {
    expect(shareText(p, 'B站搜 X')).toBe('我的2026 年 10 月创作人格：深夜写字人\n70% 的动作发生在晚上十点以后，灵感都是夜里来的\n3 个新项目 · 6 个产出 · 活跃 9 天\n给我投一票 → B站搜 X');
  });
});
