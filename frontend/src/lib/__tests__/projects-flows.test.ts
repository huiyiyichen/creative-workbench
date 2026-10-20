import { describe, expect, it } from 'vitest';
import { flowStages, qaMark } from '../projects';

const graph = {
  nodes: [
    { id: 'storyboard', label: '分镜', type: 'role' as const },
    { id: 'produce', label: '制作', type: 'role' as const },
    { id: 'qa', label: '质检', type: 'role' as const },
    { id: 'accept', label: '接受', type: 'gate' as const, enabled: false },
  ],
};
const step = (node: string, status: string, round = 1, extra: Record<string, unknown> = {}) => ({
  node,
  status,
  round,
  executor: node === 'produce' ? 'codex' : 'internal',
  error: null,
  meta: { summary: `${node}-${round}` },
  ...extra,
});

describe('flowStages', () => {
  it('取每个节点最新一轮，隐藏关闭且没跑过的关卡', () => {
    const st = flowStages(graph, [
      step('storyboard', 'done'),
      step('produce', 'done', 1),
      step('qa', 'done', 1),
      step('produce', 'running', 2),
    ]);
    expect(st.map((s) => s.id)).toEqual(['storyboard', 'produce', 'qa']);
    expect(st[1]).toMatchObject({ status: 'running', round: 2, rounds: 2, executor: 'codex', summary: 'produce-2' });
    expect(st[0].executor).toBeNull();
    expect(st[2]).toMatchObject({ status: 'done', rounds: 1 });
  });
  it('没跑过的节点是等待；关掉的关卡跑过（自动通过）时显示', () => {
    const st = flowStages(graph, [step('accept', 'done')]);
    expect(st.map((s) => s.status)).toEqual(['pending', 'pending', 'pending', 'done']);
    expect(flowStages(null, [])).toEqual([]);
  });
});

describe('qaMark', () => {
  it('通过 / 不通过 / 跳过', () => {
    expect(qaMark(true).tone).toBe('ok');
    expect(qaMark(false).text).toBe('不通过');
    expect(qaMark(null).tone).toBe('skip');
  });
});
