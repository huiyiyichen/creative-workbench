/** 随笔正文切分（纯函数）：#标签、[[双链]]、链接；代码块里的不算。与后端 notes.parse_note 规则一致。 */

export type NotePart =
  | { type: 'text'; value: string }
  | { type: 'tag'; value: string }
  | { type: 'wiki'; value: string; label: string }
  | { type: 'url'; value: string };

const TOKEN = /(\[\[[^[\]]{1,160}\]\])|(https?:\/\/[^\s)>\]]+)|((?<![\w#&])#([\w\u4e00-\u9fff][\w\u4e00-\u9fff/-]{0,30}))/gu;

export function splitNoteBody(body: string): NotePart[] {
  const out: NotePart[] = [];
  let last = 0;
  for (const m of body.matchAll(TOKEN)) {
    const idx = m.index ?? 0;
    if (idx > last) out.push({ type: 'text', value: body.slice(last, idx) });
    if (m[1]) {
      const inner = m[1].slice(2, -2);
      const [target, alias] = inner.split('|');
      out.push({ type: 'wiki', value: inner, label: alias || target });
    } else if (m[2]) {
      const url = m[2].replace(/[.,，。]+$/, '');
      out.push({ type: 'url', value: url });
      if (url.length < m[2].length) out.push({ type: 'text', value: m[2].slice(url.length) });
    } else if (m[4] && !/^\d+$/.test(m[4])) {
      out.push({ type: 'tag', value: m[4] });
    } else {
      out.push({ type: 'text', value: m[0] });
    }
    last = idx + m[0].length;
  }
  if (last < body.length) out.push({ type: 'text', value: body.slice(last) });
  return out;
}
