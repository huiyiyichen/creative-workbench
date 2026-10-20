import { describe, expect, it } from 'vitest';
import { changedCount, compareContent, compareValue, showValue } from '../compare';

describe('重跑对比', () => {
  it('长文字按段落对齐，相同段落标为一致', () => {
    const a = '第一段内容比较长，用来凑够长度。'.repeat(4) + '\n\n第二段原文。\n\n第三段不变。';
    const b = '第一段内容比较长，用来凑够长度。'.repeat(4) + '\n\n第二段改写。\n\n第三段不变。';
    const row = compareValue('body', a, b);
    expect(row.kind).toBe('text');
    if (row.kind !== 'text') return;
    expect(row.same).toBe(false);
    expect(row.rows.map((r) => r.same)).toEqual([true, false, true]);
  });

  it('对象列表按项逐字段比较，多出的项单列', () => {
    const rows = compareContent(
      { cards: [{ id: 'd1', title: 'A', angle: '教程' }], summary: '一样' },
      { cards: [{ id: 'd9', title: 'A', angle: '观点' }, { id: 'd2', title: 'B' }], summary: '一样' },
    );
    const cards = rows.find((r) => r.key === 'cards');
    expect(cards?.kind).toBe('list');
    if (cards?.kind !== 'list') return;
    expect(cards.items).toHaveLength(2);
    expect(cards.items[0].fields.find((f) => f.key === 'title')?.same).toBe(true);
    expect(cards.items[0].fields.find((f) => f.key === 'angle')?.same).toBe(false);
    expect(cards.items[0].fields.some((f) => f.key === 'id')).toBe(false);
    expect(cards.items[1].left).toBeUndefined();
    expect(changedCount(rows)).toBe(1);
  });

  it('图片并排，其他值直接比较', () => {
    expect(compareValue('image', '/media/a.png', '/media/b.png').kind).toBe('image');
    expect(compareValue('cover_url', 'https://x/c', null).kind).toBe('image');
    const v = compareValue('passed', true, false);
    expect(v.kind).toBe('value');
    expect(v.same).toBe(false);
    expect(showValue(true)).toBe('是');
    expect(showValue(['a', 'b'])).toBe('a、b');
    expect(showValue(null)).toBe('—');
  });
});
