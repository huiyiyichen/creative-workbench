import { describe, expect, it } from 'vitest';
import { docToMd, mdToDoc } from '../md-lite';
import { splitParagraphs } from '../projects';

describe('md-lite', () => {
  it('round-trips the body format', () => {
    const body = [
      '## 账单拆开看',
      '第一段有 **加粗** 和 *斜体*，引用 [1]。\n同段第二行。',
      '- 重试\n- 长上下文',
      '1. 先算\n2. 再省',
      '> 引用一句话',
      '用 `codex exec` 跑。',
    ].join('\n\n');
    const doc = mdToDoc(body);
    expect(doc.content).toHaveLength(6);
    expect(doc.content?.[0]).toMatchObject({ type: 'heading', attrs: { level: 2 } });
    expect(doc.content?.[2].type).toBe('bulletList');
    expect(docToMd(doc)).toBe(body);
  });

  it('keeps one top-level block per paragraph', () => {
    const body = '甲\n\n\n乙\n\n## 丙\n\n丁';
    expect(mdToDoc(body).content).toHaveLength(splitParagraphs(body).length);
  });

  it('drops empty paragraphs and handles empty body', () => {
    expect(mdToDoc('').content).toEqual([{ type: 'paragraph' }]);
    expect(docToMd({ type: 'doc', content: [{ type: 'paragraph' }, { type: 'paragraph', content: [{ type: 'text', text: '有字' }] }] })).toBe('有字');
  });
});
