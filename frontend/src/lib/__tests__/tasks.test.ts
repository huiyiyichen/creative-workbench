import { describe, expect, it } from 'vitest';
import { fmtDuration, groupTasks, type TaskView } from '../api/_tasks';

const t = (key: string, status: TaskView['status']) => ({ key, status }) as TaskView;

describe('任务中心', () => {
  it('按进行中 / 失败 / 完成分组，空组不显示', () => {
    const g = groupTasks([t('a', 'running'), t('b', 'done'), t('c', 'waiting'), t('d', 'stopped')]);
    expect(g.map((x) => x.id)).toEqual(['active', 'done']);
    expect(g[0].items.map((x) => x.key)).toEqual(['a', 'c']);
    expect(g[1].items.map((x) => x.key)).toEqual(['b', 'd']);
  });
  it('耗时格式', () => {
    expect(fmtDuration(null)).toBe('—');
    expect(fmtDuration(42_000)).toBe('42 秒');
    expect(fmtDuration(125_000)).toBe('2 分 5 秒');
    expect(fmtDuration(3_720_000)).toBe('1 小时 2 分');
  });
});
