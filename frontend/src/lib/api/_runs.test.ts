import { describe, expect, it } from 'vitest';
import { mergeStep, nodeStatus, nodeSteps, type StepView } from './_runs';

const step = (over: Partial<StepView>): StepView => ({
  id: 1,
  run_id: 1,
  node: 'research',
  branch: null,
  role: 'researcher',
  label: '研究员',
  executor: 'internal',
  status: 'running',
  attempt: 1,
  round: 1,
  input_artifact_ids: [],
  output_artifact_ids: [],
  model: null,
  input_tokens: 0,
  output_tokens: 0,
  cost: 0,
  started_at: '2026-10-20T03:00:00Z',
  finished_at: null,
  duration_ms: null,
  error: null,
  meta: {},
  ...over,
});

describe('运行步骤合并与节点状态', () => {
  it('同 id 覆盖，新步骤追加', () => {
    const a = [step({ id: 1 })];
    expect(mergeStep(a, step({ id: 1, status: 'done' }))[0].status).toBe('done');
    expect(mergeStep(a, step({ id: 2 }))).toHaveLength(2);
  });

  it('并行分支取每个分支最新一次尝试', () => {
    const steps = [
      step({ id: 1, branch: 'bilibili', status: 'failed' }),
      step({ id: 2, branch: 'hn', status: 'done' }),
      step({ id: 3, branch: 'bilibili', status: 'done', attempt: 2 }),
      step({ id: 4, node: 'plan' }),
    ];
    const mine = nodeSteps(steps, 'research');
    expect(mine.map((s) => s.id).sort()).toEqual([2, 3]);
    expect(nodeStatus(mine)).toBe('done');
  });

  it('节点状态优先级：失败 > 等待 > 运行 > 完成；没有步骤为未开始', () => {
    expect(nodeStatus([])).toBe('pending');
    expect(nodeStatus([step({ status: 'done' }), step({ id: 2, status: 'running' })])).toBe('running');
    expect(nodeStatus([step({ status: 'waiting' }), step({ id: 2, status: 'failed' })])).toBe('failed');
    expect(nodeStatus([step({ status: 'reused' })])).toBe('reused');
  });
});
