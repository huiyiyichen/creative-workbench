import { describe, expect, it, vi } from 'vitest';
import {
  AutosaveQueue,
  alignParagraphs,
  charDiff,
  countChars,
  fmtClock,
  joinNarration,
  moveItem,
  outline,
  overTarget,
  paragraphIndexesInRange,
  platformIssues,
  previewParagraphOps,
  shotTotal,
  splitNarration,
  emptyShot,
} from '@/lib/projects';
import type { SuggestionOp } from '@/lib/api/_projects';

const P = (id: string, text = id) => ({ id, text });

describe('字数与时长', () => {
  it('counts and formats', () => {
    expect(countChars('## 标题\n\n正文 **一段**')).toBe(6);
    expect(fmtClock(171)).toBe('2:51');
    expect(shotTotal([{ seconds: 8 }, { seconds: 20.25 }, { seconds: 18 }])).toBe(46.3);
    expect(overTarget(186, 180)).toBe(true);
    expect(overTarget(184, 180)).toBe(false);
    expect(outline('# 一\n\n正文\n\n## 二')).toEqual([
      { level: 1, text: '一', index: 0 },
      { level: 2, text: '二', index: 2 },
    ]);
  });
});

describe('建议预览', () => {
  it('overlays ops on paragraphs', () => {
    const ops: SuggestionOp[] = [
      { op_id: 'o1', op: 'replace_paragraph', id: 'a', text: 'A2' },
      { op_id: 'o2', op: 'insert_after', id: 'b', text: 'B+' },
      { op_id: 'o3', op: 'delete_paragraph', id: 'c' },
    ];
    const rows = previewParagraphOps([P('a'), P('b'), P('c')], ops);
    expect(rows.map((r) => r.kind)).toEqual(['replace', 'same', 'insert', 'delete']);
    const hidden = previewParagraphOps([P('a'), P('b'), P('c')], ops, new Set(['o1', 'o2']));
    expect(hidden.map((r) => r.kind)).toEqual(['same', 'same', 'delete']);
  });
});

describe('差异与对齐', () => {
  it('char diff', () => {
    expect(charDiff('今天天气好', '今天心情好')).toEqual([
      { type: 'eq', text: '今天' },
      { type: 'del', text: '天气' },
      { type: 'ins', text: '心情' },
      { type: 'eq', text: '好' },
    ]);
    expect(charDiff('', 'x')).toEqual([{ type: 'ins', text: 'x' }]);
    expect(charDiff('ab', 'cd', 1)).toEqual([
      { type: 'del', text: 'ab' },
      { type: 'ins', text: 'cd' },
    ]);
  });
  it('aligns by id then by position', () => {
    const rows = alignParagraphs([P('a'), P('b'), P('c'), P('d')], [P('a'), P('x'), P('c'), P('e'), P('f')]);
    expect(rows.map((r) => [r.left?.id ?? null, r.right?.id ?? null, r.same])).toEqual([
      ['a', 'a', true],
      ['b', 'x', false],
      ['c', 'c', true],
      ['d', 'e', false],
      [null, 'f', false],
    ]);
  });
});

describe('平台计数', () => {
  it('xhs issues', () => {
    const issues = platformIssues('xhs', { title: '一'.repeat(21), body: 'x', tags: ['a'], cover_text: '短' });
    expect(issues).toEqual(['标题超过 20 字（21）', '话题需要 3–8 个（现在 1）']);
    expect(platformIssues('wechat', { title: 't', body: '<p>' + '字'.repeat(10) + '</p>', summary: '' })).toEqual([]);
  });
});

describe('旁白与分镜', () => {
  it('joins and splits', () => {
    const shots = [{ ...emptyShot(), audio: '一' }, { ...emptyShot(), audio: '二' }];
    expect(joinNarration(shots)).toBe('一\n\n二');
    expect(splitNarration('甲\n\n乙', shots)?.map((s) => s.audio)).toEqual(['甲', '乙']);
    expect(splitNarration('甲', shots)).toBeNull();
    expect(moveItem([1, 2, 3], 2, 0)).toEqual([3, 1, 2]);
  });
});

describe('自动保存', () => {
  function setup(save: (v: string, t: string | null) => Promise<{ draft_token: string }>) {
    const timers: (() => void)[] = [];
    const states: string[] = [];
    const q = new AutosaveQueue<string>('t0', {
      save,
      onState: (s) => states.push(s),
      setTimer: (fn) => {
        timers.push(fn);
        return timers.length;
      },
      clearTimer: (h) => {
        timers[(h as number) - 1] = () => {};
      },
    });
    return { q, timers, states };
  }

  it('debounces and sends serially with latest token', async () => {
    const calls: [string, string | null][] = [];
    let release: (() => void) | null = null;
    const save = vi.fn((v: string, t: string | null) => {
      calls.push([v, t]);
      return new Promise<{ draft_token: string }>((res) => {
        release = () => res({ draft_token: `t${calls.length}` });
      });
    });
    const { q, timers, states } = setup(save);
    q.change('a');
    q.change('ab');
    timers.forEach((fn) => fn());
    expect(calls).toEqual([['ab', 't0']]);
    q.change('abc'); // 请求中途的新修改排队
    await q.flush(); // 有请求在途时不会并发
    expect(calls.length).toBe(1);
    release!();
    await new Promise((r) => setTimeout(r, 0));
    expect(calls).toEqual([
      ['ab', 't0'],
      ['abc', 't1'],
    ]);
    release!();
    await new Promise((r) => setTimeout(r, 0));
    expect(q.currentToken).toBe('t2');
    expect(states.at(-1)).toBe('saved');
  });

  it('enters conflict on 409 and stops until resolved', async () => {
    const err = Object.assign(new Error('另一个窗口改过'), { status: 409, code: 'draft_conflict', data: { draft_token: 'tx' } });
    const save = vi.fn().mockRejectedValueOnce(err).mockResolvedValue({ draft_token: 't9' });
    const infos: unknown[] = [];
    const q = new AutosaveQueue<string>('t0', { save, onState: (s, info) => infos.push([s, info?.token]) });
    q.change('mine');
    await q.flush();
    expect(infos.at(-1)).toEqual(['conflict', 'tx']);
    q.change('more');
    expect(q.pendingValue()).toBe('mine'); // 冲突期间不再接受新保存
    q.resolve('tx', true);
    await q.flush();
    expect(save).toHaveBeenLastCalledWith('mine', 'tx');
    expect(q.currentToken).toBe('t9');
    q.dispose();
  });
});

describe('选区到段落', () => {
  it('maps selection to paragraph indexes', () => {
    const body = '第一段\n\n第二段\n\n\n第三段';
    expect(paragraphIndexesInRange(body, 0, 2)).toEqual([0]);
    expect(paragraphIndexesInRange(body, 2, 7)).toEqual([0, 1]);
    expect(paragraphIndexesInRange(body, 6, 6)).toEqual([1]);
    expect(paragraphIndexesInRange(body, 0, body.length)).toEqual([0, 1, 2]);
  });
});
