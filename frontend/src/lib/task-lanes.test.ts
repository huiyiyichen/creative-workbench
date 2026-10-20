import { describe, expect, it } from 'vitest';
import type { TaskView } from './api/_tasks';
import { batchClips, laneClips, sortTasks } from './task-lanes';

const t = (key: string, type: string, status: string, s: string, e: string | null): TaskView =>
  ({ key, type, status, title: key, created_at: s, started_at: s, finished_at: e, duration_ms: null }) as unknown as TaskView;

describe('task-lanes', () => {
  const start = Date.parse('2026-10-21T00:00:00Z');
  const end = Date.parse('2026-10-21T10:00:00Z');
  const now = Date.parse('2026-10-21T09:00:00Z');
  it('按类型分轨、截到窗口、运行中到现在', () => {
    const m = laneClips(
      [
        t('a', 'sync', 'done', '2026-10-21T01:00:00Z', '2026-10-21T02:00:00Z'),
        t('b', 'sync', 'running', '2026-10-21T08:00:00Z', null),
        t('c', 'flow', 'failed', '2026-10-20T23:00:00Z', '2026-10-21T01:00:00Z'),
        t('d', 'flow', 'done', '2026-10-19T00:00:00Z', '2026-10-19T01:00:00Z'),
      ],
      start,
      end,
      now,
    );
    expect(m.get('sync')!.map((c) => c.key)).toEqual(['a', 'b']);
    expect(m.get('sync')![0].left).toBeCloseTo(0.1);
    expect(m.get('sync')![0].width).toBeCloseTo(0.1);
    expect(m.get('sync')![1].width).toBeCloseTo(0.1);
    expect(m.get('flow')!.map((c) => c.key)).toEqual(['c']);
    expect(m.get('flow')![0].left).toBe(0);
  });
  it('失败排前', () => {
    const s = sortTasks([t('x', 'sync', 'done', '2026-10-21T05:00:00Z', null), t('y', 'sync', 'failed', '2026-10-21T01:00:00Z', null), t('z', 'sync', 'running', '2026-10-21T02:00:00Z', null)]);
    expect(s.map((x) => x.key)).toEqual(['y', 'z', 'x']);
  });
});

describe('batchClips', () => {
  it('挨着的合成批次，失败压上面', () => {
    const c = (key: string, left: number, status: string) => ({ key, left, width: 0.001, status, title: key, task: {} }) as never;
    const b = batchClips([c('a', 0.1, 'done'), c('b', 0.102, 'failed'), c('c', 0.5, 'done')]);
    expect(b.length).toBe(2);
    expect(b[1].status).toBe('failed');
    expect(b[1].count).toBe(2);
  });
});
