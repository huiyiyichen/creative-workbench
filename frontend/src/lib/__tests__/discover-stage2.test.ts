import { describe, expect, it } from 'vitest';
import {
  bucketSeries,
  dayPosition,
  gappedPaths,
  heatOpacity,
  mediaKindColor,
  metricText,
  monthGrid,
  topPlatforms,
} from '@/lib/discover';
import { mediaColor } from '@/design/tokens';

describe('阶段 2 发现页展示逻辑', () => {
  it('时间线位置按当天 0–24 点，越界夹到两端', () => {
    const s = '2026-10-18T16:00:00Z';
    const e = '2026-10-19T16:00:00Z';
    expect(dayPosition('2026-10-19T04:00:00Z', s, e)).toBe(0.5);
    expect(dayPosition('2026-10-17T00:00:00Z', s, e)).toBe(0);
    expect(dayPosition('2026-10-20T00:00:00Z', s, e)).toBe(1);
  });

  it('热度映射亮度，缺失时中等亮度', () => {
    expect(heatOpacity(null)).toBe(0.45);
    expect(heatOpacity(0)).toBe(0.3);
    expect(heatOpacity(1)).toBe(1);
    expect(heatOpacity(5)).toBe(1);
  });

  it('指标示波：原始值 + 变化量 + 观测时间；RSS 无平台指标', () => {
    const now = new Date('2026-10-19T04:00:00Z');
    const m = metricText({ metric: 'views', value: 382000, delta: 61000, observed_at: '2026-10-19T03:20:00Z' }, now);
    expect(m).toEqual({ label: '播放', value: '38.2万', delta: '+6.1万', observed: '40 分钟前观测' });
    expect(metricText({ metric: null, state: 'RSS 无平台指标' }).value).toBe('RSS 无平台指标');
    expect(metricText({ metric: 'rank', value: 3, observed_at: '2026-10-19T03:00:00Z' }, now).value).toBe('第 3');
  });

  it('观测不足的时段断开曲线，不画 0', () => {
    const paths = gappedPaths([1, 2, null, null, 3, 4, null, 5], 100, 20);
    expect(paths).toHaveLength(2);
    expect(paths[0].startsWith('M')).toBe(true);
    expect(gappedPaths([null, 1, null], 100, 20)).toEqual([]);
  });

  it('逐小时合并：整段缺失保持 null', () => {
    expect(bucketSeries([1, 2, null, null, 3, null], 2)).toEqual([3, null, 3]);
  });

  it('平台分布取前 n、帖子用文章色、日历周一开头', () => {
    expect(topPlatforms({ hn: 1, bilibili: 5, github: 3 }, 2)).toEqual([
      ['bilibili', 5],
      ['github', 3],
    ]);
    expect(mediaKindColor('post')).toBe(mediaColor.article);
    expect(mediaKindColor('video')).toBe(mediaColor.video);
    const grid = monthGrid(2026, 10); // 2026-10-01 是周四
    expect(grid.slice(0, 4)).toEqual([null, null, null, '2026-10-01']);
    expect(grid.length % 7).toBe(0);
  });
});
