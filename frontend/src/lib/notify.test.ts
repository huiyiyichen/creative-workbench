import { describe, expect, it } from 'vitest';
import { notifyColor, notifyHref } from './notify';

describe('notifyHref', () => {
  it('优先用正文里的路径', () => {
    expect(notifyHref({ type: 'info', category: 'flow', title: '等待处理', message: '写稿（/runs/42）' })).toBe('/runs/42');
  });
  it('按类别兜底', () => {
    expect(notifyHref({ type: 'error', category: 'daily_report', title: '', message: 'x' })).toBe('/daily');
    expect(notifyHref({ type: 'auto_action', category: 'collection', title: '', message: 'x' })).toBe('/sources');
    expect(notifyHref({ type: 'info', category: 'system', title: '', message: 'x' })).toBeNull();
  });
  it('颜色', () => {
    expect(notifyColor('error')).toBe('var(--cw-rd)');
    expect(notifyColor('pipeline')).toBe('var(--cw-cy)');
  });
});
