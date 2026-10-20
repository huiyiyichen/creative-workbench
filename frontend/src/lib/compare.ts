/** 重跑对比：把两份产物内容拆成可并排比较的字段（文字按段落对齐、列表按项、图片并排、其他按值）。 */

import { alignParagraphs, splitParagraphs, type AlignedRow } from './projects';

export type CompareRow =
  | { key: string; kind: 'text'; rows: AlignedRow[]; same: boolean }
  | { key: string; kind: 'list'; items: { index: number; left: unknown; right: unknown; fields: CompareRow[]; same: boolean }[]; same: boolean }
  | { key: string; kind: 'image'; left: string | null; right: string | null; same: boolean }
  | { key: string; kind: 'value'; left: unknown; right: unknown; same: boolean };

const HIDDEN = new Set(['id', 'branch', 'branches', 'refs', 'artifact_id', 'paragraph_ids']);
const TEXT_KEYS = new Set(['body', 'markdown', 'summary', 'logline', 'notes']);
const IMAGE_RE = /\.(png|jpe?g|webp|gif)(\?|$)/i;

export const FIELD_LABEL: Record<string, string> = {
  title: '标题',
  logline: '梗概',
  body: '正文',
  summary: '摘要',
  cards: '方向卡',
  angle: '角度',
  why_now: '为什么是现在',
  format: '形式',
  findings: '发现',
  claim: '结论',
  issues: '意见',
  shots: '分镜',
  audio: '旁白',
  visual: '画面',
  prompt: '提示词',
  seconds: '时长',
  tags: '标签',
  cover_text: '封面字',
  passed: '是否通过',
  checks: '检查项',
  image: '图片',
  url: '链接',
};

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

function isImage(key: string, v: unknown): boolean {
  return typeof v === 'string' && (IMAGE_RE.test(v) || (/image|cover|keyframe/i.test(key) && /^(https?:|\/|data:image)/.test(v)));
}

function toParagraphs(text: string) {
  return splitParagraphs(text).map((t) => ({ id: t.trim(), text: t }));
}

function stable(v: unknown): string {
  return JSON.stringify(v ?? null);
}

export function compareValue(key: string, left: unknown, right: unknown): CompareRow {
  if (isImage(key, left) || isImage(key, right)) {
    return { key, kind: 'image', left: (left as string) || null, right: (right as string) || null, same: left === right };
  }
  const lt = typeof left === 'string' ? left : null;
  const rt = typeof right === 'string' ? right : null;
  if ((lt !== null || rt !== null) && (TEXT_KEYS.has(key) || /\n/.test(lt ?? '') || /\n/.test(rt ?? '') || Math.max(lt?.length ?? 0, rt?.length ?? 0) > 80)) {
    const rows = alignParagraphs(toParagraphs(lt ?? ''), toParagraphs(rt ?? ''));
    return { key, kind: 'text', rows, same: lt === rt };
  }
  const la = Array.isArray(left) ? left : null;
  const ra = Array.isArray(right) ? right : null;
  if ((la && la.some(isRecord)) || (ra && ra.some(isRecord))) {
    const n = Math.max(la?.length ?? 0, ra?.length ?? 0);
    const items = Array.from({ length: n }, (_, i) => {
      const a = la?.[i];
      const b = ra?.[i];
      const fields = isRecord(a) || isRecord(b) ? compareContent(isRecord(a) ? a : {}, isRecord(b) ? b : {}) : [];
      return { index: i, left: a, right: b, fields, same: stable(a) === stable(b) };
    });
    return { key, kind: 'list', items, same: items.every((x) => x.same) };
  }
  return { key, kind: 'value', left, right, same: stable(left) === stable(right) };
}

/** 两份产物内容逐字段比较；字段顺序先按左边，再补右边独有的。 */
export function compareContent(left: Record<string, unknown> | null, right: Record<string, unknown> | null): CompareRow[] {
  const a = left || {};
  const b = right || {};
  const keys = [...Object.keys(a), ...Object.keys(b).filter((k) => !(k in a))].filter((k) => !HIDDEN.has(k) && !k.startsWith('_'));
  return keys.map((k) => compareValue(k, a[k], b[k]));
}

export function changedCount(rows: CompareRow[]): number {
  return rows.filter((r) => !r.same).length;
}

export function showValue(v: unknown): string {
  if (v === null || v === undefined || v === '') return '—';
  if (typeof v === 'boolean') return v ? '是' : '否';
  if (Array.isArray(v) && v.every((x) => typeof x !== 'object')) return v.join('、');
  if (typeof v === 'object') return JSON.stringify(v, null, 2);
  return String(v);
}
