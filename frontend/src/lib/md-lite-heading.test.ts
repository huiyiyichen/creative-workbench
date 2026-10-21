import { describe, expect, it } from 'vitest';
import { docToMd, mdToDoc } from './md-lite';

describe('小标题不空行', () => {
  it('「## 标题\\n正文」拆成标题 + 段落', () => {
    const doc = mdToDoc('## 切入场景\n第一句。\n第二句。\n\n## 横评方法');
    expect(doc.content!.map((n) => n.type)).toEqual(['heading', 'paragraph', 'heading']);
    expect(docToMd(doc)).toBe('## 切入场景\n\n第一句。\n第二句。\n\n## 横评方法');
  });
});
