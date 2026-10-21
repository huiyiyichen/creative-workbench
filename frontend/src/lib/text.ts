/**
 * 文本小工具：HTML 实体解码、搜索命中切分。
 * 抓回来的标题 / 摘要里常带 `&#8217;`、`&amp;` 这类实体，在 API 适配层统一解码，组件里不用各自处理。
 */

const NAMED: Record<string, string> = {
  amp: '&',
  lt: '<',
  gt: '>',
  quot: '"',
  apos: "'",
  nbsp: '\u00a0',
  hellip: '…',
  mdash: '—',
  ndash: '–',
  lsquo: '‘',
  rsquo: '’',
  ldquo: '“',
  rdquo: '”',
  middot: '·',
  copy: '©',
  reg: '®',
  trade: '™',
};

/** 解码 HTML 实体（命名、十进制、十六进制）；不认识的原样保留。纯函数，服务端也能跑 */
export function decodeEntities<T extends string | null | undefined>(text: T): T {
  if (!text || text.indexOf('&') < 0) return text;
  return text.replace(/&(#x[0-9a-f]+|#\d+|[a-z]+);/gi, (whole, body: string) => {
    if (body[0] === '#') {
      const code = body[1] === 'x' || body[1] === 'X' ? parseInt(body.slice(2), 16) : parseInt(body.slice(1), 10);
      return Number.isFinite(code) && code > 0 && code <= 0x10ffff ? String.fromCodePoint(code) : whole;
    }
    return NAMED[body.toLowerCase()] ?? whole;
  }) as T;
}

/** 对象里指定字段解码，返回新对象 */
export function decodeFields<T extends object>(obj: T, keys: readonly (keyof T)[]): T {
  const out = { ...obj };
  for (const k of keys) {
    const v = out[k];
    if (typeof v === 'string') (out as Record<keyof T, unknown>)[k] = decodeEntities(v);
  }
  return out;
}

const escapeRe = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

export type HitPart = { text: string; hit: boolean };

/**
 * 把文本按命中词切开，标出全部命中。
 * 拉丁字母 / 数字的查询按整词匹配（搜「AI」不染 said、main），中文等按子串匹配。
 */
export function splitHits(text: string, q: string): HitPart[] {
  const words = q.trim().split(/\s+/).filter(Boolean);
  if (!text || !words.length) return [{ text, hit: false }];
  const pats = words.map((w) => {
    const e = escapeRe(w);
    return /^[\p{Script=Latin}\d_-]+$/u.test(w) ? `(?<![\\p{Script=Latin}\\d])${e}(?![\\p{Script=Latin}\\d])` : e;
  });
  const re = new RegExp(pats.join('|'), 'giu');
  const parts: HitPart[] = [];
  let last = 0;
  for (const m of text.matchAll(re)) {
    const i = m.index ?? 0;
    if (!m[0]) continue;
    if (i > last) parts.push({ text: text.slice(last, i), hit: false });
    parts.push({ text: m[0], hit: true });
    last = i + m[0].length;
  }
  if (last < text.length) parts.push({ text: text.slice(last), hit: false });
  return parts.length ? parts : [{ text, hit: false }];
}

/** 按键去重，保留第一次出现 */
export function uniqBy<T>(list: readonly T[], key: (x: T) => string): T[] {
  const seen = new Set<string>();
  return list.filter((x) => {
    const k = key(x);
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  });
}

const COMBINING: Record<string, string> = { '"': '\u0308', "'": '\u0301', '`': '\u0300', '^': '\u0302', '~': '\u0303', '=': '\u0304', '.': '\u0307', c: '\u0327', u: '\u0306', v: '\u030c', H: '\u030b', k: '\u0328', r: '\u030a' };
const LETTERS: Record<string, string> = { ss: 'ß', o: 'ø', O: 'Ø', l: 'ł', L: 'Ł', ae: 'æ', AE: 'Æ', oe: 'œ', OE: 'Œ', aa: 'å', AA: 'Å', i: 'ı' };

/** BibTeX 重音转义 → Unicode（arXiv 作者名 `\"Ozayta\c{c}` → `Özaytaç`）。后端新入库已处理，这里兜存量数据 */
export function delatex<T extends string | null | undefined>(text: T): T {
  if (!text || text.indexOf('\\') < 0) return text;
  let out = (text as string).replace(/\\(["'`^~=.])\s*(?:\{\s*(\\?[A-Za-z])\s*\}|(\\?[A-Za-z]))|\\([cuvHkr])(?:\s*\{\s*(\\?[A-Za-z])\s*\}|\s+([A-Za-z]))/g, (_w, c1, a, b, c2, d, e) => {
    const cmd = (c1 || c2) as string;
    let ch = (a || b || d || e) as string;
    if (ch.startsWith('\\')) ch = ch.slice(1) === 'i' ? (`"'\`^~=`.includes(cmd) ? 'i' : 'ı') : ch.slice(1);
    return (ch + COMBINING[cmd]).normalize('NFC');
  });
  out = out.replace(/\\(ss|ae|AE|oe|OE|aa|AA|o|O|l|L|i)(?![A-Za-z])(?:\{\})?/g, (_w, k: string) => LETTERS[k]);
  out = out.replace(/\{([^{}\\]{1,3})\}/g, '$1');
  return out as T;
}

const TEXT_KEYS = new Set(['title', 'title_zh', 'title_cn', 'snippet', 'summary', 'summary_zh', 'headline', 'excerpt', 'description']);

/** 深度遍历 API 返回值，把标题 / 摘要类字段里的 HTML 实体解码（原地改，返回同一对象） */
export function decodeTextDeep<T>(value: T): T {
  if (Array.isArray(value)) {
    for (const v of value) decodeTextDeep(v);
  } else if (value && typeof value === 'object') {
    const rec = value as Record<string, unknown>;
    for (const k of Object.keys(rec)) {
      const v = rec[k];
      if (typeof v === 'string') {
        if (TEXT_KEYS.has(k)) rec[k] = delatex(decodeEntities(v));
        else if (k === 'author' || k === 'authors') rec[k] = delatex(v);
      } else if (v && typeof v === 'object') decodeTextDeep(v);
    }
  }
  return value;
}
