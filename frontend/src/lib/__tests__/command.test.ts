import { describe, expect, it } from 'vitest';
import { filterCommands, scoreMatch, type CommandItem } from '../command';

const items: CommandItem[] = [
  { id: 'a', label: '灵感库', group: '页面', keywords: 'library lgk' },
  { id: 'b', label: '新建项目', group: '操作', keywords: 'new project xjxm' },
  { id: 'c', label: '项目', group: '页面', keywords: 'projects xm' },
  { id: 'd', label: '海边的旅行视频', group: '项目' },
];

describe('scoreMatch', () => {
  it('连续包含得分最高，开头更高', () => {
    expect(scoreMatch('项目', '项目')).toBeGreaterThan(scoreMatch('新建项目', '项目'));
  });
  it('子序列也能命中', () => {
    expect(scoreMatch('海边的旅行视频', '海视')).toBeGreaterThan(0);
  });
  it('不命中返回 -1', () => {
    expect(scoreMatch('灵感库', '飞书')).toBe(-1);
  });
});

describe('filterCommands', () => {
  it('空查询按原顺序截断', () => {
    expect(filterCommands(items, '', 2).map((x) => x.id)).toEqual(['a', 'b']);
  });
  it('按分数排序', () => {
    expect(filterCommands(items, '项目').map((x) => x.id)).toEqual(['c', 'b']);
  });
  it('关键词（英文 / 拼音首字母）也能搜到', () => {
    expect(filterCommands(items, 'lgk').map((x) => x.id)).toEqual(['a']);
    expect(filterCommands(items, 'new').map((x) => x.id)).toEqual(['b']);
  });
});
