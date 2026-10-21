import { describe, expect, it } from 'vitest';
import { decodeEntities, splitHits, uniqBy } from './text';

describe('decodeEntities', () => {
  it('解码数字和命名实体', () => {
    expect(decodeEntities('you&#8217;re &amp; me &#x2014; &hellip;')).toBe('you’re & me — …');
  });
  it('不认识的原样保留，空值透传', () => {
    expect(decodeEntities('&foo; a&b')).toBe('&foo; a&b');
    expect(decodeEntities(null)).toBe(null);
  });
});

describe('splitHits', () => {
  const hits = (t: string, q: string) => splitHits(t, q).filter((p) => p.hit).map((p) => p.text);
  it('英文按整词匹配并命中全部', () => {
    expect(hits('He said AI is the main AI story; Chairman ai', 'AI')).toEqual(['AI', 'AI', 'ai']);
  });
  it('中文按子串', () => {
    expect(hits('生成式AI与AI视频', '视频')).toEqual(['视频']);
    expect(hits('生成式AI与AI视频', 'AI')).toEqual(['AI', 'AI']);
  });
  it('多个词、拼回原文', () => {
    const parts = splitHits('Open source LLM tools', 'llm open');
    expect(parts.map((p) => p.text).join('')).toBe('Open source LLM tools');
    expect(parts.filter((p) => p.hit).length).toBe(2);
  });
});

it('uniqBy 保留第一次', () => {
  expect(uniqBy([{ k: 'a', n: 1 }, { k: 'a', n: 2 }, { k: 'b', n: 3 }], (x) => x.k).map((x) => x.n)).toEqual([1, 3]);
});

it('decodeTextDeep 只动标题摘要类字段', async () => {
  const { decodeTextDeep } = await import('./text');
  const v = decodeTextDeep({ items: [{ title: 'a&#8217;b', url: 'x?a=1&amp;b=2', meta: { summary: '&lt;p&gt;' } }] });
  expect(v.items[0].title).toBe('a’b');
  expect(v.items[0].url).toBe('x?a=1&amp;b=2');
  expect(v.items[0].meta.summary).toBe('<p>');
});
