import { describe, expect, it } from 'vitest';
import { anchorLabel, countLeaves } from '@/design/lineage';

describe('溯源', () => {
  it('锚点名称', () => {
    expect(anchorLabel('shot_3')).toBe('第 3 镜');
    expect(anchorLabel('p_1a2b3c4d')).toBe('段落');
    expect(anchorLabel('d2')).toBe('方向 2');
    expect(anchorLabel(null)).toBeNull();
  });
  it('统计追到的采集内容、灵感库与网页（去重）', () => {
    const n = (type: string, id: number | null, sources: unknown[] = [], url: string | null = null) =>
      ({ relation: 'cites', type, id, url, anchor: null, target_anchor: null, sources }) as never;
    const tree = [n('artifact', 1, [n('content', 5), n('library', 7), n('content', 5)]), n('url', null, [], 'https://a'), n('content', 6)];
    expect(countLeaves(tree)).toEqual({ content: 2, library: 1, url: 1 });
  });
});
