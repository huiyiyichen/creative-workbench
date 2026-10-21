import { describe, expect, it } from 'vitest';
import { heatLabel, memeProjectHref } from './memes';

describe('memes', () => {
  it('开稿链接带主题和创作思路', () => {
    const href = memeProjectHref({ word: '班味', meaning: '上班的疲惫感', usage: '周末去班味', origin: '' });
    const u = new URL(href, 'http://x');
    expect(u.pathname).toBe('/projects/new');
    expect(u.searchParams.get('theme')).toBe('班味');
    expect(u.searchParams.get('intent')).toBe('用今天的梗「班味」写一篇\n意思：上班的疲惫感\n示范用法：周末去班味');
  });
  it('热度文案', () => {
    expect([heatLabel(1), heatLabel(2), heatLabel(3)]).toEqual(['冒头', '升温', '正火']);
  });
});
