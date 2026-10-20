import { describe, expect, it } from 'vitest';
import { splitNoteBody } from '@/lib/notes';

describe('随笔正文切分', () => {
  it('标签、双链（含别名）、链接、纯数字不算标签', () => {
    const parts = splitNoteBody('想到 #选题 和 [[包豪斯海报|海报]] 见 https://ex.com/a。 #12');
    expect(parts.filter((p) => p.type === 'tag')).toEqual([{ type: 'tag', value: '选题' }]);
    expect(parts.find((p) => p.type === 'wiki')).toEqual({ type: 'wiki', value: '包豪斯海报|海报', label: '海报' });
    expect(parts.find((p) => p.type === 'url')).toEqual({ type: 'url', value: 'https://ex.com/a' });
    expect(parts.map((p) => ('label' in p ? p.label : p.value)).join('')).toBe('想到 选题 和 海报 见 https://ex.com/a。 #12');
  });
});
