/**
 * 创作工作台纯逻辑（设计文档 5、6、13 节）：字数与时长、段落、建议预览、段落对齐与差异、
 * 平台计数、旁白与分镜对应、自动保存队列。全部可单测，不依赖 DOM。
 */
import type { Draft, Paragraph, Shot, SuggestionOp } from '@/lib/api/_projects';

// ── 字数 / 时长 ──

/** 正文字数：去掉空白与常见 Markdown 记号后按字符计。 */
export function countChars(text: string): number {
  return (text || '').replace(/[#>*_`~\-[\]()!|]/g, '').replace(/\s+/g, '').length;
}

/** 中文朗读约每分钟 250 字。 */
export function readSeconds(chars: number): number {
  return Math.round((chars / 250) * 60);
}

export function fmtClock(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
}

export function shotTotal(shots: Pick<Shot, 'seconds'>[]): number {
  return Math.round(shots.reduce((sum, s) => sum + (Number(s.seconds) || 0), 0) * 10) / 10;
}

/** 超出目标 3% 以上算超时（时长条变黄）。 */
export function overTarget(total: number, target: number): boolean {
  return target > 0 && total > target * 1.03;
}

// ── 段落 ──

export function splitParagraphs(body: string): string[] {
  return (body || '')
    .split(/\n\s*\n/)
    .map((p) => p.replace(/^\n+|\n+$/g, ''))
    .filter((p) => p.trim());
}

/** 文本选区 [start, end) 覆盖到的段落序号（按 splitParagraphs 的切分）；光标落在段落里也算。 */
export function paragraphIndexesInRange(body: string, start: number, end: number): number[] {
  const re = /\n\s*\n/g;
  const spans: [number, number][] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(body)) !== null) {
    spans.push([last, m.index]);
    last = m.index + m[0].length;
  }
  spans.push([last, body.length]);
  const nonEmpty = spans.filter(([a, b]) => body.slice(a, b).trim());
  const lo = Math.min(start, end);
  const hi = Math.max(start, end);
  return nonEmpty.flatMap(([a, b], i) => ((lo < b && hi > a) || (lo === hi && lo >= a && lo <= b) ? [i] : []));
}

export interface OutlineEntry {
  level: number;
  text: string;
  index: number; // 段落序号
}

export function outline(body: string): OutlineEntry[] {
  return splitParagraphs(body).flatMap((p, index) => {
    const m = /^(#{1,3})\s+(.+)/.exec(p.trim());
    return m ? [{ level: m[1].length, text: m[2].trim(), index }] : [];
  });
}

// ── 建议预览 ──

export type PreviewRow =
  | { kind: 'same'; id: string; text: string }
  | { kind: 'replace'; id: string; old: string; text: string; op_id: string; reason?: string }
  | { kind: 'delete'; id: string; old: string; op_id: string; reason?: string }
  | { kind: 'insert'; after: string; text: string; op_id: string; reason?: string };

/** 把段落操作叠到当前段落上，生成修订样式的行；已处理的 op 不再显示。 */
export function previewParagraphOps(paragraphs: Paragraph[], ops: SuggestionOp[], hidden: Set<string> = new Set()): PreviewRow[] {
  const live = ops.filter((o) => !hidden.has(o.op_id));
  const rows: PreviewRow[] = [];
  for (const p of paragraphs) {
    const rep = live.find((o) => (o.op === 'replace_paragraph' || o.op === 'delete_paragraph') && o.id === p.id);
    if (rep?.op === 'replace_paragraph') rows.push({ kind: 'replace', id: p.id, old: p.text, text: rep.text, op_id: rep.op_id, reason: rep.reason });
    else if (rep?.op === 'delete_paragraph') rows.push({ kind: 'delete', id: p.id, old: p.text, op_id: rep.op_id, reason: rep.reason });
    else rows.push({ kind: 'same', id: p.id, text: p.text });
    for (const ins of live) {
      if (ins.op === 'insert_after' && ins.id === p.id) rows.push({ kind: 'insert', after: p.id, text: ins.text, op_id: ins.op_id, reason: ins.reason });
    }
  }
  return rows;
}

export function shotOps(ops: SuggestionOp[]): SuggestionOp[] {
  return ops.filter((o) => o.op.endsWith('_shot'));
}

export function describeShotOp(op: SuggestionOp): string {
  switch (op.op) {
    case 'update_shot':
      return `第 ${op.index + 1} 镜 · ${SHOT_FIELD_LABEL[op.field] || op.field} → ${op.value}`;
    case 'insert_shot':
      return `在第 ${op.after + 1} 镜后插入：${op.shot.visual || op.shot.beat}`;
    case 'delete_shot':
      return `删除第 ${op.index + 1} 镜`;
    case 'move_shot':
      return `第 ${op.from + 1} 镜移到第 ${op.to + 1} 位`;
    default:
      return '';
  }
}

export const SHOT_FIELD_LABEL: Record<string, string> = {
  seconds: '时长',
  beat: '名称',
  visual: '画面',
  camera: '镜头与运动',
  audio: '旁白',
  caption: '字幕',
  transition: '衔接',
  prompt: '提示词',
};

// ── 差异 ──

export type DiffPart = { type: 'eq' | 'del' | 'ins'; text: string };

/** 按字符的 LCS 差异；太长时整段替换，避免卡界面。 */
export function charDiff(a: string, b: string, limit = 4_000_000): DiffPart[] {
  if (a === b) return a ? [{ type: 'eq', text: a }] : [];
  const n = a.length;
  const m = b.length;
  if (!n) return [{ type: 'ins', text: b }];
  if (!m) return [{ type: 'del', text: a }];
  if (n * m > limit) return [{ type: 'del', text: a }, { type: 'ins', text: b }];
  const dp: Uint32Array[] = Array.from({ length: n + 1 }, () => new Uint32Array(m + 1));
  for (let i = n - 1; i >= 0; i--) {
    for (let k = m - 1; k >= 0; k--) {
      dp[i][k] = a[i] === b[k] ? dp[i + 1][k + 1] + 1 : Math.max(dp[i + 1][k], dp[i][k + 1]);
    }
  }
  const parts: DiffPart[] = [];
  const push = (type: DiffPart['type'], ch: string) => {
    const last = parts[parts.length - 1];
    if (last && last.type === type) last.text += ch;
    else parts.push({ type, text: ch });
  };
  let i = 0;
  let k = 0;
  while (i < n && k < m) {
    if (a[i] === b[k]) {
      push('eq', a[i]);
      i++;
      k++;
    } else if (dp[i + 1][k] >= dp[i][k + 1]) {
      push('del', a[i++]);
    } else {
      push('ins', b[k++]);
    }
  }
  while (i < n) push('del', a[i++]);
  while (k < m) push('ins', b[k++]);
  return parts;
}

export interface AlignedRow {
  left: Paragraph | null;
  right: Paragraph | null;
  same: boolean;
}

/** 段落对齐：先按 id（内容哈希）做最长公共子序列匹配；两次匹配之间未匹配的段落按顺序配对（视为改动），多出的单列。 */
export function alignParagraphs(left: Paragraph[], right: Paragraph[]): AlignedRow[] {
  const n = left.length;
  const m = right.length;
  const dp: number[][] = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) {
    for (let k = m - 1; k >= 0; k--) {
      dp[i][k] = left[i].id === right[k].id ? dp[i + 1][k + 1] + 1 : Math.max(dp[i + 1][k], dp[i][k + 1]);
    }
  }
  const rows: AlignedRow[] = [];
  let pendL: Paragraph[] = [];
  let pendR: Paragraph[] = [];
  const flushPending = () => {
    const len = Math.max(pendL.length, pendR.length);
    for (let x = 0; x < len; x++) rows.push({ left: pendL[x] ?? null, right: pendR[x] ?? null, same: false });
    pendL = [];
    pendR = [];
  };
  let i = 0;
  let k = 0;
  while (i < n && k < m) {
    if (left[i].id === right[k].id) {
      flushPending();
      rows.push({ left: left[i], right: right[k], same: true });
      i++;
      k++;
    } else if (dp[i + 1][k] >= dp[i][k + 1]) {
      pendL.push(left[i++]);
    } else {
      pendR.push(right[k++]);
    }
  }
  while (i < n) pendL.push(left[i++]);
  while (k < m) pendR.push(right[k++]);
  flushPending();
  return rows;
}

export function diffCount(rows: AlignedRow[]): number {
  return rows.filter((r) => !r.same).length;
}

// ── 平台计数（与后端 output_rules 一致）──

export const PLATFORM_LIMITS: Record<string, { title?: number; body?: number; cover_text?: number; summary?: number; tags?: [number, number] }> = {
  xhs: { title: 20, body: 1000, cover_text: 12, tags: [3, 8] },
  zhihu: { title: 100, body: 20000 },
  wechat: { title: 64, body: 20000, summary: 120 },
};

export function textLen(text: string | null | undefined): number {
  return (text || '').trim().length;
}

export function stripTags(html: string): string {
  return (html || '').replace(/<[^>]+>/g, '');
}

export function platformIssues(kind: string, c: { title?: string; body?: string; cover_text?: string; summary?: string; tags?: string[] }): string[] {
  const lim = PLATFORM_LIMITS[kind];
  if (!lim) return [];
  const out: string[] = [];
  const check = (label: string, value: string | undefined, max?: number) => {
    const n = textLen(value);
    if (max !== undefined && n > max) out.push(`${label}超过 ${max} 字（${n}）`);
  };
  check('标题', c.title, lim.title);
  check('正文', kind === 'wechat' ? stripTags(c.body || '') : c.body, lim.body);
  check('封面文案', c.cover_text, lim.cover_text);
  check('摘要', c.summary, lim.summary);
  if (lim.tags) {
    const n = (c.tags || []).length;
    if (n < lim.tags[0] || n > lim.tags[1]) out.push(`话题需要 ${lim.tags[0]}–${lim.tags[1]} 个（现在 ${n}）`);
  }
  return out;
}

// ── 旁白 ↔ 分镜 ──

export function joinNarration(shots: Pick<Shot, 'audio'>[]): string {
  return shots.map((s) => s.audio.trim()).filter(Boolean).join('\n\n');
}

/** 旁白全文按段落写回各镜；段落数与分镜数不一致时返回 null（界面提示「按段落重新分镜」）。 */
export function splitNarration(text: string, shots: Shot[]): Shot[] | null {
  const paras = splitParagraphs(text);
  if (paras.length !== shots.length) return null;
  return shots.map((s, i) => ({ ...s, audio: paras[i] }));
}

export function emptyShot(): Shot {
  return { seconds: 5, beat: '', visual: '', camera: '', audio: '', transition: '直切', caption: '', prompt: '' };
}

export function moveItem<T>(list: T[], from: number, to: number): T[] {
  if (from === to || from < 0 || to < 0 || from >= list.length || to >= list.length) return list;
  const next = list.slice();
  const [item] = next.splice(from, 1);
  next.splice(to, 0, item);
  return next;
}

export function draftEquals(a: Draft, b: Draft): boolean {
  return a.title === b.title && a.logline === b.logline && a.body === b.body && JSON.stringify(a.shots) === JSON.stringify(b.shots);
}

// ── 自动保存队列 ──

export type AutosaveState = 'idle' | 'pending' | 'saving' | 'saved' | 'conflict' | 'error';

export interface AutosaveDeps<T> {
  save: (value: T, token: string | null) => Promise<{ draft_token: string }>;
  onState: (state: AutosaveState, info?: { token?: string; error?: string; savedAt?: number }) => void;
  delay?: number;
  setTimer?: (fn: () => void, ms: number) => unknown;
  clearTimer?: (h: unknown) => void;
  now?: () => number;
}

/**
 * 自动保存：防抖（默认 1.5 秒）、串行发送（同一时间只有一个请求，期间的新修改排到下一次）、
 * 收到 409 draft_conflict 进入冲突状态并停止保存，直到 resolve()。
 */
export class AutosaveQueue<T> {
  private token: string | null;
  private timer: unknown = null;
  private inflight = false;
  private queued: T | null = null;
  private stopped = false;
  private deps: Required<Omit<AutosaveDeps<T>, 'save' | 'onState'>> & Pick<AutosaveDeps<T>, 'save' | 'onState'>;

  constructor(token: string | null, deps: AutosaveDeps<T>) {
    this.token = token;
    this.deps = {
      delay: 1500,
      setTimer: (fn, ms) => setTimeout(fn, ms),
      clearTimer: (h) => clearTimeout(h as ReturnType<typeof setTimeout>),
      now: () => Date.now(),
      ...deps,
    };
  }

  get currentToken(): string | null {
    return this.token;
  }

  setToken(token: string | null): void {
    this.token = token;
  }

  get busy(): boolean {
    return this.inflight || this.queued !== null || this.timer !== null;
  }

  change(value: T): void {
    if (this.stopped) return;
    this.queued = value;
    if (this.timer !== null) this.deps.clearTimer(this.timer);
    this.deps.onState('pending');
    this.timer = this.deps.setTimer(() => {
      this.timer = null;
      void this.flush();
    }, this.deps.delay);
  }

  /** 立即保存待存内容（例如离开页面、保存版本前）。 */
  async flush(): Promise<void> {
    if (this.timer !== null) {
      this.deps.clearTimer(this.timer);
      this.timer = null;
    }
    if (this.inflight || this.queued === null || this.stopped) return;
    const value = this.queued;
    this.queued = null;
    this.inflight = true;
    this.deps.onState('saving');
    try {
      const r = await this.deps.save(value, this.token);
      this.token = r.draft_token;
      this.inflight = false;
      if (this.queued !== null) {
        await this.flush();
      } else {
        this.deps.onState('saved', { token: this.token, savedAt: this.deps.now() });
      }
    } catch (err) {
      this.inflight = false;
      const e = err as Error & { status?: number; code?: string; data?: Record<string, unknown> };
      if (e.status === 409 && e.code === 'draft_conflict') {
        this.stopped = true;
        this.queued = value;
        this.deps.onState('conflict', { token: (e.data?.draft_token as string) || undefined, error: e.message });
      } else {
        this.queued = this.queued ?? value;
        this.deps.onState('error', { error: e.message });
      }
    }
  }

  /** 冲突处理后恢复：载入最新时丢弃本地待存；覆盖时用新 token 继续发送。 */
  resolve(token: string, keepPending: boolean): void {
    this.token = token;
    this.stopped = false;
    if (!keepPending) this.queued = null;
  }

  pendingValue(): T | null {
    return this.queued;
  }

  dispose(): void {
    if (this.timer !== null) this.deps.clearTimer(this.timer);
    this.timer = null;
    this.stopped = true;
  }
}

// ── 流程阶段条（成稿 / 成片）──

export interface FlowStage {
  id: string;
  label: string;
  type: 'role' | 'gate';
  status: 'pending' | 'running' | 'done' | 'failed' | 'waiting' | 'reused' | 'stopped';
  round: number;
  rounds: number;
  executor: string | null;
  summary: string | null;
  error: string | null;
}

interface StageStep {
  node: string;
  status: string;
  round: number;
  executor: string;
  error: string | null;
  meta: { summary?: string } & Record<string, unknown>;
}

/** 按模板节点顺序汇总步骤：取每个节点最新一轮（退回循环时轮次 > 1） */
export function flowStages(
  graph: { nodes: { id: string; label: string; type: 'role' | 'gate'; enabled?: boolean }[] } | null | undefined,
  steps: StageStep[],
): FlowStage[] {
  if (!graph) return [];
  return graph.nodes
    .filter((n) => n.type !== 'gate' || n.enabled !== false || steps.some((s) => s.node === n.id))
    .map((n) => {
      const mine = steps.filter((s) => s.node === n.id);
      const last = mine[mine.length - 1];
      const rounds = mine.reduce((m, s) => Math.max(m, s.round || 1), 0);
      return {
        id: n.id,
        label: n.label,
        type: n.type,
        status: (last?.status as FlowStage['status']) || 'pending',
        round: last?.round || 0,
        rounds,
        executor: last && last.executor !== 'internal' && last.executor !== 'human' ? last.executor : null,
        summary: (last?.meta?.summary as string | undefined) || null,
        error: last?.error || null,
      };
    });
}

export const ACTIVE_RUN = ['queued', 'running', 'waiting'];

/** 质检报告里每项的显示：通过 / 不通过 / 跳过 */
export function qaMark(ok: boolean | null): { text: string; tone: 'ok' | 'bad' | 'skip' } {
  if (ok === null) return { text: '跳过', tone: 'skip' };
  return ok ? { text: '通过', tone: 'ok' } : { text: '不通过', tone: 'bad' };
}
