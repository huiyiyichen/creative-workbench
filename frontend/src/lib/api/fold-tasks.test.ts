import { describe, expect, it } from 'vitest';
import { foldTasks, type TaskView } from './_tasks';

const t = (key: string, status: TaskView['status'], extra: Partial<TaskView> = {}): TaskView =>
  ({ key, type: 'sync', kind: 'sync', kind_label: '采集', title: key, project_id: null, project_title: null, output_title: null, status, raw_status: status, stage: null, created_at: '', started_at: null, finished_at: null, duration_ms: null, cost: 0, reason: null, hint: null, href: '/', can_stop: false, can_retry: true, ...extra }) as TaskView;

describe('foldTasks', () => {
  it('同原因失败 ≥3 折成一行，放在第一条的位置', () => {
    const items = [t('a', 'running'), t('f1', 'failed', { reason: '超时' }), t('b', 'done'), t('f2', 'failed', { reason: '超时' }), t('f3', 'failed', { reason: '超时' }), t('f4', 'failed', { reason: '403' })];
    const out = foldTasks(items);
    expect(out.map((e) => (e.kind === 'one' ? e.task.key : `fold:${e.tasks.length}`))).toEqual(['a', 'fold:3', 'b', 'f4']);
  });
  it('同标题完成 ≥2 折叠，进行中不折', () => {
    const items = [t('x', 'done', { title: 'Gemini' }), t('r', 'running', { title: 'Gemini' }), t('y', 'done', { title: 'Gemini' })];
    expect(foldTasks(items).map((e) => e.kind)).toEqual(['fold', 'one']);
  });
});
