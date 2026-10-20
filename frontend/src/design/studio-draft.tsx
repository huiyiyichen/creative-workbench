'use client';

/**
 * 文稿步骤部件（设计文档 5 节）：分镜表 ScriptTable、建议审阅 SuggestionReview、AI 助手 AssistantPanel、
 * 版本 VersionsPanel、版本对比 VersionCompare、来源 SourcesPanel。
 */

import { Input, InputNumber, Modal, message } from 'antd';
import { LineageDrawer } from './lineage';
import type { LineageQuery } from '@/lib/api/_runs';
import { ArrowDown, ArrowUp, Copy, Plus, Trash2 } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Button } from './components';
import { apiError, reasonLabel } from './studio';
import { platformName } from './discover';
import {
  SHOT_FIELD_LABEL,
  alignParagraphs,
  charDiff,
  describeShotOp,
  diffCount,
  emptyShot,
  fmtClock,
  moveItem,
  overTarget,
  previewParagraphOps,
  shotOps,
  shotTotal,
  type AlignedRow,
} from '@/lib/projects';
import {
  projectsApi,
  type Draft,
  type Paragraph,
  type ProjectSource,
  type Shot,
  type Suggestion,
  type SuggestionScope,
  type VersionItem,
  type VersionView,
} from '@/lib/api/_projects';

// ── 分镜表 ──

const MAIN_COLS: (keyof Shot)[] = ['visual', 'camera', 'audio', 'caption'];
const MORE_COLS: (keyof Shot)[] = ['beat', 'prompt', 'transition'];

export function ScriptTable({
  shots,
  target,
  readOnly,
  selected,
  onSelect,
  onChange,
}: {
  shots: Shot[];
  target: number;
  readOnly: boolean;
  selected: number[];
  onSelect: (idx: number[]) => void;
  onChange: (shots: Shot[]) => void;
}) {
  const [open, setOpen] = useState<number | null>(null);
  const total = shotTotal(shots);
  const set = (i: number, field: keyof Shot, value: string | number) =>
    onChange(shots.map((s, k) => (k === i ? { ...s, [field]: value } : s)));
  const insert = (after: number) => onChange([...shots.slice(0, after + 1), emptyShot(), ...shots.slice(after + 1)]);
  const dup = (i: number) => onChange([...shots.slice(0, i + 1), { ...shots[i] }, ...shots.slice(i + 1)]);
  const del = (i: number) => onChange(shots.filter((_, k) => k !== i));
  const pct = target > 0 ? Math.min(100, (total / target) * 100) : 0;
  return (
    <div className="cw-script">
      <table className="cw-shots">
        <thead>
          <tr>
            <th>镜</th>
            <th>时长</th>
            {MAIN_COLS.map((c) => (
              <th key={c}>{SHOT_FIELD_LABEL[c]}</th>
            ))}
            <th aria-label="操作" />
          </tr>
        </thead>
        <tbody>
          {shots.map((s, i) => (
            <FragmentRow key={i}>
              <tr
                data-selected={selected.includes(i) || undefined}
                onClick={(e) => onSelect(e.shiftKey || e.metaKey || e.ctrlKey ? Array.from(new Set([...selected, i])) : [i])}
                onKeyDown={(e) => {
                  if (!e.altKey || readOnly) return;
                  if (e.key === 'ArrowUp' && i > 0) {
                    e.preventDefault();
                    onChange(moveItem(shots, i, i - 1));
                    onSelect([i - 1]);
                  } else if (e.key === 'ArrowDown' && i < shots.length - 1) {
                    e.preventDefault();
                    onChange(moveItem(shots, i, i + 1));
                    onSelect([i + 1]);
                  }
                }}
              >
                <td className="cw-num">
                  <button type="button" className="cw-link-btn" onClick={() => setOpen(open === i ? null : i)} aria-expanded={open === i} title="展开全部字段">
                    {i + 1}
                  </button>
                </td>
                <td>
                  <InputNumber
                    size="small"
                    className="cw-num"
                    min={0.1}
                    max={600}
                    step={0.5}
                    value={s.seconds}
                    disabled={readOnly}
                    onChange={(v) => set(i, 'seconds', Number(v) || 0.1)}
                    style={{ width: 72 }}
                  />
                </td>
                {MAIN_COLS.map((c) => (
                  <td key={c}>
                    <Input.TextArea
                      variant="borderless"
                      autoSize={{ minRows: 1, maxRows: 6 }}
                      value={String(s[c] ?? '')}
                      readOnly={readOnly}
                      onChange={(e) => set(i, c, e.target.value)}
                      aria-label={`第 ${i + 1} 镜${SHOT_FIELD_LABEL[c]}`}
                    />
                  </td>
                ))}
                <td className="cw-shot-actions">
                  {!readOnly ? (
                    <>
                      <button type="button" aria-label="上移" disabled={i === 0} onClick={() => onChange(moveItem(shots, i, i - 1))}>
                        <ArrowUp size={13} />
                      </button>
                      <button type="button" aria-label="下移" disabled={i === shots.length - 1} onClick={() => onChange(moveItem(shots, i, i + 1))}>
                        <ArrowDown size={13} />
                      </button>
                      <button type="button" aria-label="在后面插入" onClick={() => insert(i)}>
                        <Plus size={13} />
                      </button>
                      <button type="button" aria-label="复制" onClick={() => dup(i)}>
                        <Copy size={13} />
                      </button>
                      <button type="button" aria-label="删除" onClick={() => del(i)}>
                        <Trash2 size={13} />
                      </button>
                    </>
                  ) : null}
                </td>
              </tr>
              {open === i ? (
                <tr className="cw-shot-more">
                  <td />
                  <td colSpan={MAIN_COLS.length + 2}>
                    <div className="cw-brief">
                      {MORE_COLS.map((c) => (
                        <label key={c} className={c === 'prompt' ? 'cw-brief-wide' : undefined}>
                          <span>{SHOT_FIELD_LABEL[c]}</span>
                          <Input.TextArea autoSize={{ minRows: 1, maxRows: 8 }} value={String(s[c] ?? '')} readOnly={readOnly} onChange={(e) => set(i, c, e.target.value)} />
                        </label>
                      ))}
                    </div>
                  </td>
                </tr>
              ) : null}
            </FragmentRow>
          ))}
        </tbody>
      </table>
      {!readOnly ? (
        <Button onClick={() => insert(shots.length - 1)} icon={<Plus size={14} />}>
          加一镜
        </Button>
      ) : null}
      <div className="cw-durbar" data-over={overTarget(total, target) || undefined}>
        <span className="cw-num">总时长 {fmtClock(total)}</span>
        <span className="cw-durbar-track">
          <i style={{ width: `${pct}%` }} />
        </span>
        <span className="cw-num">目标 {fmtClock(target)}</span>
      </div>
    </div>
  );
}

function FragmentRow({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}

// ── 建议审阅（修订样式）──

export function SuggestionReview({
  suggestion,
  paragraphs,
  shots,
  onDone,
}: {
  suggestion: Suggestion;
  paragraphs: Paragraph[];
  shots: Shot[];
  onDone: (result?: { draft: Draft; version: number; token: string }) => void;
}) {
  const [busy, setBusy] = useState(false);
  const handled = useMemo(() => new Set(suggestion.applied_ops), [suggestion.applied_ops]);
  const [rejected, setRejected] = useState<Set<string>>(new Set());
  const hidden = useMemo(() => new Set([...handled, ...rejected]), [handled, rejected]);
  const rows = previewParagraphOps(paragraphs, suggestion.ops, hidden);
  const sOps = shotOps(suggestion.ops).filter((o) => !hidden.has(o.op_id));
  const remaining = suggestion.ops.filter((o) => !hidden.has(o.op_id));
  const accept = async (ids?: string[]) => {
    setBusy(true);
    try {
      const r = await projectsApi.applySuggestion(suggestion.id, ids ?? remaining.map((o) => o.op_id));
      if (r.conflicts?.length) message.warning(`${r.conflicts.length} 处因为文稿已改动没能应用`);
      const left = suggestion.ops.filter((o) => !r.applied_ops.includes(o.op_id) && !rejected.has(o.op_id) && !(r.conflicts || []).includes(o.op_id));
      if (!left.length) {
        if (rejected.size) await projectsApi.rejectSuggestion(suggestion.id).catch(() => undefined);
        onDone({ draft: r.draft.draft, version: r.version, token: r.draft_token });
      } else {
        onDone({ draft: r.draft.draft, version: r.version, token: r.draft_token });
      }
    } catch (err) {
      message.error(apiError(err));
    } finally {
      setBusy(false);
    }
  };
  const rejectOne = (opId: string) => {
    const next = new Set(rejected).add(opId);
    setRejected(next);
    if (suggestion.ops.every((o) => handled.has(o.op_id) || next.has(o.op_id))) void rejectAll();
  };
  const rejectAll = async () => {
    setBusy(true);
    try {
      await projectsApi.rejectSuggestion(suggestion.id);
      onDone();
    } catch (err) {
      message.error(apiError(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="cw-review">
      <div className="cw-review-head">
        <b>AI 建议</b>
        <span className="cw-muted">{suggestion.instructions}</span>
        <span className="cw-grow" />
        <span className="cw-num cw-muted">剩 {remaining.length} 处</span>
        <Button variant="primary" disabled={busy || !remaining.length} onClick={() => accept()}>
          全部接受
        </Button>
        <Button disabled={busy} onClick={rejectAll}>
          全部拒绝
        </Button>
      </div>
      <div className="cw-paper">
        {rows.map((r, i) =>
          r.kind === 'same' ? (
            <p key={`s${i}`}>{r.text}</p>
          ) : (
            <div key={r.op_id} className="cw-rev" data-kind={r.kind}>
              {r.kind !== 'insert' ? <p className="cw-rev-del">{r.old}</p> : null}
              {r.kind !== 'delete' ? <p className="cw-rev-ins">{r.text}</p> : null}
              <div className="cw-rev-act">
                {r.reason ? <small>{r.reason}</small> : null}
                <button type="button" disabled={busy} onClick={() => accept([r.op_id])}>
                  接受
                </button>
                <button type="button" disabled={busy} onClick={() => rejectOne(r.op_id)}>
                  拒绝
                </button>
              </div>
            </div>
          ),
        )}
      </div>
      {sOps.length ? (
        <ul className="cw-rev-shots">
          {sOps.map((o) => (
            <li key={o.op_id}>
              <span>{describeShotOp(o)}</span>
              {o.op === 'update_shot' && shots[o.index] ? <small className="cw-muted">原：{String(shots[o.index][o.field])}</small> : null}
              <button type="button" disabled={busy} onClick={() => accept([o.op_id])}>
                接受
              </button>
              <button type="button" disabled={busy} onClick={() => rejectOne(o.op_id)}>
                拒绝
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

// ── AI 助手 ──

const QUICK = [
  { key: 'colloquial', label: '更口语' },
  { key: 'formal', label: '更正式' },
  { key: 'compress', label: '压缩到 600 字', n: 600 },
  { key: 'new_opening', label: '换个开头' },
  { key: 'add_example', label: '加一个例子' },
  { key: 'template', label: '按模板重排' },
  { key: 'cite', label: '补充来源依据' },
];
const STATUS_TXT: Record<string, string> = { pending: '待处理', applied: '已接受', partial: '部分接受', rejected: '已拒绝' };

export function AssistantPanel({
  projectId,
  scope,
  disabled,
  beforeSend,
  onSuggestion,
  refreshKey,
}: {
  projectId: number;
  scope: SuggestionScope;
  disabled: string | null;
  beforeSend: () => Promise<{ token: string | null; scope: SuggestionScope }>;
  onSuggestion: (s: Suggestion) => void;
  refreshKey: number;
}) {
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<Suggestion[]>([]);
  const load = useCallback(async () => {
    try {
      setHistory((await projectsApi.suggestions(projectId)).items);
    } catch {
      /* 历史加载失败不影响使用 */
    }
  }, [projectId]);
  useEffect(() => {
    void load();
  }, [load, refreshKey]);
  const send = async (quick?: { key: string; n?: number }) => {
    if (!quick && !text.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const prep = await beforeSend();
      const s = await projectsApi.suggest(projectId, {
        scope: prep.scope,
        instructions: quick ? '' : text,
        quick: quick?.key,
        n: quick?.n,
        draft_token: prep.token,
      });
      if (!quick) setText('');
      onSuggestion(s);
      await load();
    } catch (err) {
      setError(apiError(err, 'AI 修改失败'));
    } finally {
      setBusy(false);
    }
  };
  const scopeText = scope.type === 'paragraphs' ? `选中的 ${scope.ids?.length || 0} 段` : scope.type === 'shots' ? `选中的 ${scope.indexes?.length || 0} 镜` : '全文';
  return (
    <div className="cw-assist">
      <p className="cw-muted">
        修改范围：<b>{scopeText}</b>（在编辑器里选中文字或分镜会自动切换）
      </p>
      {disabled ? <div className="cw-notice">{disabled}</div> : null}
      <div className="cw-chips">
        {QUICK.map((q) => (
          <button key={q.key} type="button" className="cw-btn" disabled={busy || Boolean(disabled)} onClick={() => send(q)}>
            {q.label}
          </button>
        ))}
      </div>
      <Input.TextArea
        value={text}
        onChange={(e) => setText(e.target.value)}
        autoSize={{ minRows: 3, maxRows: 8 }}
        placeholder="自由指令，例如：第二段补一个具体数字"
        maxLength={2000}
        disabled={busy || Boolean(disabled)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
            e.preventDefault();
            void send();
          }
        }}
      />
      <div className="cw-row" style={{ justifyContent: 'flex-end', marginTop: 6 }}>
        <Button variant="primary" disabled={busy || !text.trim() || Boolean(disabled)} onClick={() => send()}>
          {busy ? '生成中…' : '发送 Ctrl⏎'}
        </Button>
      </div>
      {error ? (
        <div className="cw-error">
          {error}{' '}
          {/model|模型/.test(error) ? (
            <a href="/admin/model-eval" className="cw-link-btn">
              配置模型
            </a>
          ) : null}
        </div>
      ) : null}
      <h4 className="cw-detail-h">历史</h4>
      <ul className="cw-hist">
        {history.map((h) => (
          <li key={h.id}>
            <button type="button" className="cw-link-btn" onClick={() => onSuggestion(h)} disabled={h.status === 'applied' || h.status === 'rejected'}>
              <span className="cw-num">{new Date(h.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}</span> {h.instructions.slice(0, 24)}
            </button>
            <small data-status={h.status}>{STATUS_TXT[h.status] || h.status}</small>
          </li>
        ))}
        {!history.length ? <li className="cw-empty">还没有 AI 修改</li> : null}
      </ul>
    </div>
  );
}

// ── 版本 ──

export function VersionsPanel({
  projectId,
  refreshKey,
  current,
  onRestored,
  readOnly,
}: {
  projectId: number;
  refreshKey: number;
  current: { draft: Draft; paragraphs: Paragraph[] };
  onRestored: () => void;
  readOnly: boolean;
}) {
  const [items, setItems] = useState<VersionItem[]>([]);
  const [preview, setPreview] = useState<VersionView | null>(null);
  const [compare, setCompare] = useState<VersionView | null>(null);
  const [lin, setLin] = useState<LineageQuery | null>(null);
  useEffect(() => {
    projectsApi
      .versions(projectId)
      .then((r) => setItems(r.items))
      .catch(() => setItems([]));
  }, [projectId, refreshKey]);
  const open = async (v: number) => setPreview(await projectsApi.version(projectId, v));
  const restore = async (v: number) => {
    try {
      await projectsApi.restore(projectId, v);
      message.success(`已恢复为 v${v}（生成了新版本）`);
      setCompare(null);
      setPreview(null);
      onRestored();
    } catch (err) {
      message.error(apiError(err));
    }
  };
  return (
    <div className="cw-versions">
      <ul className="cw-hist">
        {items.map((v) => (
          <li key={v.version} data-active={preview?.version === v.version || undefined}>
            <button type="button" className="cw-link-btn" onClick={() => open(v.version)}>
              <b className="cw-num">v{v.version}</b> {reasonLabel(v.reason)} {v.finalized ? '🔒' : ''}
            </button>
            <small className="cw-num">{new Date(v.created_at).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</small>
          </li>
        ))}
        {!items.length ? <li className="cw-empty">还没有版本。自动保存只写工作副本，「保存版本」才会出现在这里。</li> : null}
      </ul>
      {preview ? (
        <div className="cw-vpreview">
          <div className="cw-row">
            <b className="cw-num">v{preview.version}</b>
            <span className="cw-muted">{reasonLabel(preview.reason)}</span>
            <span className="cw-grow" />
            <Button onClick={() => setLin({ target: 'version', project_id: projectId, version: preview.version })}>溯源</Button>
            <Button onClick={() => setCompare(preview)}>与当前对比</Button>
          </div>
          <div className="cw-vpreview-body">
            <h4>{preview.draft.title}</h4>
            {preview.paragraphs.slice(0, 12).map((p) => (
              <p
                key={p.id}
                className="cw-vpara"
                title="点这一段看它的来源"
                role="button"
                tabIndex={0}
                onClick={() => setLin({ target: 'paragraph', project_id: projectId, version: preview.version, anchor: p.id })}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') setLin({ target: 'paragraph', project_id: projectId, version: preview.version, anchor: p.id });
                }}
              >
                {p.text}
              </p>
            ))}
            {preview.draft.shots.length ? <p className="cw-muted">分镜 {preview.draft.shots.length} 镜 · {fmtClock(shotTotal(preview.draft.shots))}</p> : null}
          </div>
        </div>
      ) : null}
      <LineageDrawer query={lin} onClose={() => setLin(null)} title={lin?.target === 'paragraph' ? '溯源：这一段' : '溯源：文稿版本'} />
      {compare ? (
        <VersionCompare
          left={compare}
          right={current}
          onClose={() => setCompare(null)}
          onRestore={readOnly ? undefined : () => restore(compare.version)}
        />
      ) : null}
    </div>
  );
}

function Diffed({ a, b, side }: { a: string; b: string; side: 'left' | 'right' }) {
  const parts = charDiff(a, b);
  return (
    <>
      {parts.map((p, i) =>
        p.type === 'eq' ? (
          <span key={i}>{p.text}</span>
        ) : (p.type === 'del') === (side === 'left') ? (
          <mark key={i} data-kind={p.type}>
            {p.text}
          </mark>
        ) : null,
      )}
    </>
  );
}

export function VersionCompare({
  left,
  right,
  onClose,
  onRestore,
}: {
  left: VersionView;
  right: { draft: Draft; paragraphs: Paragraph[] };
  onClose: () => void;
  onRestore?: () => void;
}) {
  const rows: AlignedRow[] = alignParagraphs(left.paragraphs, right.paragraphs);
  const diffIdx = rows.map((r, i) => (r.same ? -1 : i)).filter((i) => i >= 0);
  const [cursor, setCursor] = useState(0);
  const jump = (dir: 1 | -1) => {
    if (!diffIdx.length) return;
    const next = (cursor + dir + diffIdx.length) % diffIdx.length;
    setCursor(next);
    document.getElementById(`cmp-row-${diffIdx[next]}`)?.scrollIntoView({ block: 'center', behavior: 'smooth' });
  };
  const maxShots = Math.max(left.draft.shots.length, right.draft.shots.length);
  return (
    <Modal open onCancel={onClose} width="96vw" footer={null} title={`v${left.version} 与当前对比`} className="cw-compare-modal" destroyOnHidden>
      <div className="cw-row" style={{ marginBottom: 10 }}>
        <span className="cw-num cw-muted">{diffCount(rows)} 处段落差异</span>
        <Button onClick={() => jump(-1)} disabled={!diffIdx.length}>
          上一处
        </Button>
        <Button onClick={() => jump(1)} disabled={!diffIdx.length}>
          下一处
        </Button>
        <span className="cw-grow" />
        {onRestore ? (
          <Button variant="primary" onClick={onRestore}>
            恢复为这个版本
          </Button>
        ) : null}
      </div>
      <div className="cw-compare">
        <div className="cw-compare-h">v{left.version}</div>
        <div className="cw-compare-h">当前</div>
        {rows.map((r, i) => (
          <div key={i} id={`cmp-row-${i}`} className="cw-compare-row" data-same={r.same || undefined}>
            <p>{r.left ? r.right && !r.same ? <Diffed a={r.left.text} b={r.right.text} side="left" /> : r.left.text : <i className="cw-muted">（无）</i>}</p>
            <p>{r.right ? r.left && !r.same ? <Diffed a={r.left.text} b={r.right.text} side="right" /> : r.right.text : <i className="cw-muted">（无）</i>}</p>
          </div>
        ))}
        {Array.from({ length: maxShots }).map((_, i) => {
          const a = left.draft.shots[i];
          const b = right.draft.shots[i];
          const same = JSON.stringify(a) === JSON.stringify(b);
          return (
            <div key={`s${i}`} className="cw-compare-row" data-same={same || undefined}>
              {[a, b].map((s, k) => (
                <div key={k} className="cw-compare-shot">
                  <b className="cw-num">第 {i + 1} 镜</b>
                  {s
                    ? (['seconds', 'visual', 'camera', 'audio', 'caption'] as (keyof Shot)[]).map((f) => (
                        <div key={f} data-changed={(a && b && String(a[f]) !== String(b[f])) || undefined}>
                          <small>{SHOT_FIELD_LABEL[f]}</small> {String(s[f] ?? '')}
                        </div>
                      ))
                    : <i className="cw-muted">（无）</i>}
                </div>
              ))}
            </div>
          );
        })}
      </div>
    </Modal>
  );
}

// ── 来源 ──

export function SourcesPanel({ sources, onInsertCite, onInsertQuote }: { sources: ProjectSource[]; onInsertCite: (n: number) => void; onInsertQuote: (text: string) => void }) {
  const [open, setOpen] = useState<number | null>(null);
  return (
    <ol className="cw-srclist">
      {sources.map((s, i) => (
        <li key={s.id}>
          <button type="button" className="cw-link-btn" onClick={() => setOpen(open === s.id ? null : s.id)} aria-expanded={open === s.id}>
            [{i + 1}] {s.snapshot.title}
          </button>
          <small className="cw-muted">
            {s.role === 'main' ? '主来源' : '参考'} · {platformName(s.snapshot.platform)}
          </small>
          {open === s.id ? (
            <div className="cw-srclist-body">
              {s.snapshot.summary ? <p>{s.snapshot.summary}</p> : <p className="cw-muted">没有摘要</p>}
              <div className="cw-row">
                <Button onClick={() => onInsertCite(i + 1)}>插入引用</Button>
                {s.snapshot.summary ? (
                  <Button
                    onClick={() => {
                      const sel = typeof window !== 'undefined' ? window.getSelection()?.toString() : '';
                      onInsertQuote(sel || (s.snapshot.summary || '').slice(0, 200));
                    }}
                  >
                    插入摘录
                  </Button>
                ) : null}
                {s.snapshot.url ? (
                  <a className="cw-btn" data-variant="ghost" href={s.snapshot.url} target="_blank" rel="noreferrer">
                    原文 ↗
                  </a>
                ) : null}
              </div>
            </div>
          ) : null}
        </li>
      ))}
      {!sources.length ? <li className="cw-empty">项目没有来源</li> : null}
    </ol>
  );
}
