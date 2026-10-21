import { describe, expect, it } from 'vitest';
import { breakdownIntent, isUrl, wordTier } from './breakdown';

describe('breakdown helpers', () => {
  it('创作思路文字', () => {
    const t = breakdownIntent({ title: '爆款', verdict: '反差', hook: { text: '第一句', type: '反差', why: '' }, template: '1. a' });
    expect(t).toBe('参考爆款：爆款\n它为什么火：反差\n钩子（反差）：第一句\n\n照这个结构写：\n1. a');
    expect(breakdownIntent({ title: 'x', verdict: '', hook: { text: '', type: '', why: '' }, template: '' })).toBe('参考爆款：x');
  });
  it('热词档位与链接识别', () => {
    expect(wordTier(0, 5)).toBe(0);
    expect(wordTier(5, 5)).toBe(3);
    expect(wordTier(2, 6)).toBe(1);
    expect(isUrl(' https://b23.tv/abc ')).toBe(true);
    expect(isUrl('打工人')).toBe(false);
  });
});
