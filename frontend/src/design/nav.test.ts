import { describe, expect, it } from 'vitest';
import { CW_NAV, CW_NAV_BOTTOM, activeNavId } from './nav';

describe('主导航', () => {
  it('分区与 11.1 一致', () => {
    expect(CW_NAV.map((g) => g.items.map((i) => i.label))).toEqual([
      ['今日', '热点', '报告', '专题'],
      ['灵感库'],
      ['项目'],
      ['作品', '任务', '花费'],
    ]);
    expect(CW_NAV_BOTTOM.map((i) => i.label)).toEqual(['信源', '设置']);
  });

  it('按最长前缀判断当前入口', () => {
    expect(activeNavId('/')).toBe('today');
    expect(activeNavId('/items/3')).toBe('today');
    expect(activeNavId('/weekly')).toBe('reports');
    expect(activeNavId('/sources')).toBe('sources');
    expect(activeNavId('/admin/sources')).toBe('sources');
    expect(activeNavId('/admin/settings')).toBe('settings');
    expect(activeNavId('/stats/jobs')).toBe('tasks');
    expect(activeNavId('/runs/3')).toBe('tasks');
    expect(activeNavId('/admin/contents')).toBe('sources');
    expect(activeNavId('/works')).toBe('works');
  });
});
