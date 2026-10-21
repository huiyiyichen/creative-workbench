/**
 * 正文的轻量 Markdown ↔ TipTap 文档互转。正文仍以纯文本存储（空一行分段、「## 」小标题、引用 [1]），
 * 段落序号与后端段落 id 一一对应：文档的每个顶层块就是一段。
 * 支持：段落（单换行为软换行）、# / ## / ### 小标题、- 无序列表、1. 有序列表、> 引用、**加粗**、*斜体*、`代码`。
 */

export interface PMMark {
  type: string;
}
export interface PMNode {
  type: string;
  attrs?: Record<string, unknown>;
  content?: PMNode[];
  text?: string;
  marks?: PMMark[];
}

const INLINE = /(\*\*([^*\n]+)\*\*|\*([^*\n]+)\*|`([^`\n]+)`)/g;

export function parseInline(text: string): PMNode[] {
  const out: PMNode[] = [];
  const lines = text.split('\n');
  lines.forEach((line, li) => {
    if (li) out.push({ type: 'hardBreak' });
    let last = 0;
    for (const m of line.matchAll(INLINE)) {
      const at = m.index ?? 0;
      if (at > last) out.push({ type: 'text', text: line.slice(last, at) });
      if (m[2] !== undefined) out.push({ type: 'text', text: m[2], marks: [{ type: 'bold' }] });
      else if (m[3] !== undefined) out.push({ type: 'text', text: m[3], marks: [{ type: 'italic' }] });
      else out.push({ type: 'text', text: m[4], marks: [{ type: 'code' }] });
      last = at + m[0].length;
    }
    if (last < line.length) out.push({ type: 'text', text: line.slice(last) });
  });
  return out;
}

function para(text: string): PMNode {
  const content = parseInline(text);
  return content.length ? { type: 'paragraph', content } : { type: 'paragraph' };
}

function blockToNode(block: string): PMNode {
  const lines = block.split('\n');
  const h = /^(#{1,3})\s+(.*)$/.exec(block);
  if (h && lines.length === 1) return { type: 'heading', attrs: { level: h[1].length }, content: parseInline(h[2]) };
  if (lines.every((l) => /^[-*]\s+/.test(l))) {
    return { type: 'bulletList', content: lines.map((l) => ({ type: 'listItem', content: [para(l.replace(/^[-*]\s+/, ''))] })) };
  }
  if (lines.every((l) => /^\d+[.)]\s+/.test(l))) {
    return { type: 'orderedList', content: lines.map((l) => ({ type: 'listItem', content: [para(l.replace(/^\d+[.)]\s+/, ''))] })) };
  }
  if (lines.every((l) => /^>\s?/.test(l))) {
    return { type: 'blockquote', content: [para(lines.map((l) => l.replace(/^>\s?/, '')).join('\n'))] };
  }
  return para(block);
}

/**
 * 小标题行单独成块：模型 / 粘贴来的正文常写成「## 标题\n正文」不空行，
 * 不拆开的话整块会当成段落、编辑器里露出「## 」字面量。
 */
export function splitHeadingLines(block: string): string[] {
  const out: string[] = [];
  let buf: string[] = [];
  for (const line of block.split('\n')) {
    if (/^#{1,3}\s+\S/.test(line)) {
      if (buf.length) out.push(buf.join('\n'));
      out.push(line);
      buf = [];
    } else buf.push(line);
  }
  if (buf.length) out.push(buf.join('\n'));
  return out.filter((p) => p.trim());
}

export function mdToDoc(body: string): PMNode {
  const blocks = (body || '')
    .split(/\n\s*\n/)
    .map((p) => p.replace(/^\n+|\n+$/g, ''))
    .filter((p) => p.trim())
    .flatMap(splitHeadingLines);
  return { type: 'doc', content: blocks.length ? blocks.map(blockToNode) : [{ type: 'paragraph' }] };
}

export function inlineToMd(nodes: PMNode[] | undefined): string {
  return (nodes || [])
    .map((n) => {
      if (n.type === 'hardBreak') return '\n';
      const t = n.text || '';
      const marks = new Set((n.marks || []).map((m) => m.type));
      if (!t) return '';
      if (marks.has('code')) return `\`${t}\``;
      let s = t;
      if (marks.has('italic')) s = `*${s}*`;
      if (marks.has('bold')) s = `**${s}**`;
      return s;
    })
    .join('');
}

function itemText(item: PMNode): string {
  return (item.content || []).map((c) => inlineToMd(c.content)).join(' ').replace(/\n/g, ' ');
}

export function nodeToMd(n: PMNode): string {
  switch (n.type) {
    case 'heading':
      return `${'#'.repeat(Number(n.attrs?.level) || 2)} ${inlineToMd(n.content).replace(/\n/g, ' ')}`;
    case 'bulletList':
      return (n.content || []).map((it) => `- ${itemText(it)}`).join('\n');
    case 'orderedList':
      return (n.content || []).map((it, i) => `${i + 1}. ${itemText(it)}`).join('\n');
    case 'blockquote':
      return (n.content || [])
        .map((c) => inlineToMd(c.content))
        .join('\n')
        .split('\n')
        .map((l) => `> ${l}`)
        .join('\n');
    default:
      return inlineToMd(n.content);
  }
}

/** 文档 → 正文：每个顶层块一段，块之间空一行；空段落丢掉。 */
export function docToMd(doc: PMNode): string {
  return (doc.content || [])
    .map(nodeToMd)
    .filter((s) => s.trim())
    .join('\n\n');
}
