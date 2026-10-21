'use client';

/**
 * 创作工作台共用部件（设计文档 3、4、8 节）：项目上下文、项目栏 ProjectShell、灵感库选择器 AssetPicker、
 * 来源选择器 SourcePicker、情绪板 MoodBoard。
 */

import { EmptyInstrument, SignalPath } from './instrument';
import { FeishuButton } from './feishu';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Checkbox, Input, Modal, Switch, message } from 'antd';
import { Lock, Pencil } from 'lucide-react';
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import { Button, Cover, SearchField } from './components';
import { ImageGenPanel } from './imagegen';
import { color, mediaColor } from './tokens';
import { platformName } from './discover';
import { discoverApi, type ItemCard } from '@/lib/api/_discover';
import { libraryApi, libraryFileUrl, type LibraryItem } from '@/lib/api/_library';
import { mediaUrl } from '@/lib/api/_collection';
import { projectsApi, type PipelineView, type OutputKind, type ProjectAsset, type ProjectMode, type ProjectSource, type ProjectView } from '@/lib/api/_projects';
import { runsApi, type RunDetail } from '@/lib/api/_runs';
import { ACTIVE_RUN, flowStages, type FlowStage } from '@/lib/projects';
import { METRIC_LABEL, compactNumber } from '@/lib/collection';

export const MODE_LABEL: Record<ProjectMode, string> = {
  article: '文章',
  animation_video: '动画讲解',
  video_prompt: '视频',
  music_video: '音乐 MV',
};
export const MODE_COLOR: Record<ProjectMode, string> = {
  article: mediaColor.article,
  animation_video: mediaColor.video,
  video_prompt: mediaColor.video,
  music_video: mediaColor.video,
};
export const OUTPUT_LABEL: Record<OutputKind, string> = {
  xhs: '小红书版',
  zhihu: '知乎版',
  wechat: '公众号版',
  video: '讲解视频',
  mv: '音乐 MV',
  prompt_bundle: '视频提示词包',
};
export const OUTPUT_STATUS: Record<string, [string, string]> = {
  draft: ['草稿', color.dim],
  rendering: ['制作中', color.cy],
  done: ['完成', color.gr],
  failed: ['失败', color.rd],
  exported: ['已导出', color.bl],
  published: ['已发布', color.wh],
};
export const STAGE_LABEL = { idea: '选题与创意', draft: '文稿', outputs: '产出' } as const;
const STAGE_ORDER = ['idea', 'draft', 'outputs'] as const;
export const VERSION_REASON: Record<string, string> = {
  manual: '保存版本',
  finalized: '定稿',
  compiled: '按模板生成',
  ai: 'AI 初稿',
  ai_suggestion: 'AI 建议',
  overwritten: '覆盖前备份',
  created: '创建',
  edited: '编辑',
  refined: 'AI 修改',
};
export function reasonLabel(reason: string): string {
  if (reason.startsWith('restored:')) return `恢复自 ${reason.slice(9)}`;
  return VERSION_REASON[reason] || reason;
}

export function apiError(err: unknown, fallback = '操作失败'): string {
  return err instanceof Error && err.message ? err.message : fallback;
}

// ── 项目上下文 ──

interface ProjectCtx {
  project: ProjectView | null;
  error: string | null;
  reload: () => Promise<ProjectView | null>;
  setProject: (p: ProjectView) => void;
  /** 文稿页把未保存状态报给项目栏（黄点） */
  unsaved: boolean;
  setUnsaved: (v: boolean) => void;
}

const Ctx = createContext<ProjectCtx | null>(null);

export function useProject(): ProjectCtx {
  const v = useContext(Ctx);
  if (!v) throw new Error('useProject 只能在项目页面里用');
  return v;
}

export function ProjectProvider({ id, children }: { id: number; children: ReactNode }) {
  const [project, setProject] = useState<ProjectView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [unsaved, setUnsaved] = useState(false);
  const reload = useCallback(async () => {
    try {
      const p = await projectsApi.get(id);
      setProject(p);
      setError(null);
      return p;
    } catch (err) {
      setError(apiError(err, '项目加载失败'));
      return null;
    }
  }, [id]);
  useEffect(() => {
    void reload();
  }, [reload]);
  const value = useMemo(() => ({ project, error, reload, setProject, unsaved, setUnsaved }), [project, error, reload, unsaved]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

// ── 项目栏 ──

function StatusMark({ project, unsaved }: { project: ProjectView; unsaved: boolean }) {
  // 「未保存」只指工作副本还没写进数据库；自动保存后只是「没存成版本」，两者分开说，避免和底栏的「已自动保存」打架。
  const base = project.finalized_version ? `已定稿 v${project.finalized_version}` : '草稿';
  if (unsaved) {
    return (
      <span className="cw-pstatus" data-tone="dirty" title="修改还在写入工作副本">
        <i /> {base} · 未保存
      </span>
    );
  }
  if (project.status === 'dirty') {
    return (
      <span className="cw-pstatus" data-tone="draft" title="修改已自动保存到工作副本，还没有存成版本">
        <i /> {base} · 未存版本
      </span>
    );
  }
  if (project.status === 'finalized') {
    return (
      <span className="cw-pstatus" data-tone="final">
        <Lock size={12} aria-hidden /> 已定稿 v{project.finalized_version}
      </span>
    );
  }
  return <span className="cw-pstatus">草稿{project.version ? ` v${project.version}` : ''}</span>;
}

const PIPE_ACTIVE = ['research', 'draft', 'awaiting_finalize', 'producing'];
const PIPE_OUTPUTS = [
  { value: 'video', label: '讲解视频' },
  { value: 'xhs', label: '小红书' },
  { value: 'zhihu', label: '知乎' },
  { value: 'wechat', label: '公众号' },
];

function pipelineRun(p: PipelineView): number | undefined {
  const r = p.runs || {};
  if (p.stage === 'research') return r.research;
  if (p.stage === 'draft' || p.stage === 'awaiting_finalize') return r.draft;
  return r.platforms ?? r.produce?.[0] ?? r.draft;
}

/** 一键全流程：启动弹窗 + 进度条（运行中每 4 秒刷新项目） */
function Pipeline() {
  const { project, reload } = useProject();
  const [open, setOpen] = useState(false);
  const [outputs, setOutputs] = useState<string[]>(PIPE_OUTPUTS.map((o) => o.value));
  const [choose, setChoose] = useState(true);
  const [accept, setAccept] = useState(true);
  const [busy, setBusy] = useState(false);
  const p = project?.pipeline || {};
  const active = PIPE_ACTIVE.includes(p.stage || '');
  useEffect(() => {
    if (!active || p.stage === 'awaiting_finalize') return;
    const t = setInterval(() => void reload(), 4000);
    return () => clearInterval(t);
  }, [active, p.stage, reload]);
  if (!project) return null;
  const start = async () => {
    setBusy(true);
    try {
      await projectsApi.startPipeline(project.id, { outputs, choose_gate: choose, accept_gate: accept });
      setOpen(false);
      await reload();
    } catch (err) {
      message.error(apiError(err, '全流程没有启动'));
    } finally {
      setBusy(false);
    }
  };
  const stop = async () => {
    try {
      await projectsApi.stopPipeline(project.id);
      await reload();
    } catch (err) {
      message.error(apiError(err));
    }
  };
  const runId = p.stage ? pipelineRun(p) : undefined;
  return (
    <>
      {p.stage ? (
        <span className="cw-pipe" data-stage={p.stage} title={p.reason || undefined}>
          <i aria-hidden />
          全流程 · {p.stage_label}
          {p.stage === 'awaiting_finalize' ? (
            <Link className="cw-link-btn" href={`/projects/${project.id}/draft`}>
              去定稿
            </Link>
          ) : null}
          {runId ? (
            <Link className="cw-link-btn" href={`/runs/${runId}`}>
              {p.stage === 'research' ? '选方向 / 过程' : '过程'}
            </Link>
          ) : null}
          {active ? (
            <button type="button" className="cw-link-btn" onClick={stop}>
              停止
            </button>
          ) : null}
        </span>
      ) : null}
      {!active && !project.finalized_version ? (
        <button type="button" className="cw-pbar-link cw-link-btn" onClick={() => setOpen(true)}>
          一键全流程
        </button>
      ) : null}
      <Modal title="一键全流程" open={open} onCancel={() => setOpen(false)} onOk={start} okText="开始" cancelText="取消" confirmLoading={busy} okButtonProps={{ disabled: !outputs.length }}>
        <p className="cw-muted">选题研究 → 选方向 → 成稿 → 接受 → 你来定稿 → 讲解视频与平台版本同时开始。定稿始终由你确认。</p>
        <div className="cw-stack" style={{ display: 'grid', gap: 12 }}>
          <Checkbox.Group value={outputs} onChange={(v) => setOutputs(v as string[])} options={PIPE_OUTPUTS} />
          <label className="cw-row" style={{ gap: 8 }}>
            <Switch size="small" checked={choose} onChange={setChoose} /> 停下来让我选方向（关闭则用第一个方向）
          </label>
          <label className="cw-row" style={{ gap: 8 }}>
            <Switch size="small" checked={accept} onChange={setAccept} /> 成稿后让我确认是否接受（关闭则直接写成新版本）
          </label>
        </div>
      </Modal>
    </>
  );
}

export function ProjectShell({ children }: { children: ReactNode }) {
  const { project, error, setProject, unsaved } = useProject();
  const pathname = usePathname();
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState('');
  if (error)
    return (
      <div className="cw-page">
        <EmptyInstrument
          kind="unplugged"
          title={/not found|不存在/.test(error) ? '这个项目不存在或已被删除' : '项目没加载出来'}
          reason={/not found|不存在/.test(error) ? '可能是在别处删掉了，或者链接里的编号不对。' : error}
          actions={
            <Link className="cw-btn" data-variant="primary" href="/projects">
              回到项目
            </Link>
          }
        />
      </div>
    );
  if (!project) return <div className="cw-page cw-empty">加载中…</div>;
  const base = `/projects/${project.id}`;
  const step = pathname.includes('/outputs') ? 'outputs' : pathname.endsWith('/draft') ? 'draft' : 'idea';
  const canDraft = Boolean(project.brief.theme);
  const saveTitle = async () => {
    setEditing(false);
    const t = title.trim();
    if (!t || t === project.title) return;
    try {
      setProject(await projectsApi.rename(project.id, t));
    } catch (err) {
      message.error(apiError(err));
    }
  };
  const steps: { id: keyof typeof STAGE_LABEL; href: string; disabled?: string }[] = [
    { id: 'idea', href: `${base}/idea` },
    { id: 'draft', href: `${base}/draft`, disabled: canDraft ? undefined : '先写一个主题' },
    { id: 'outputs', href: `${base}/outputs` },
  ];
  return (
    <div className="cw-project">
      <header className="cw-pbar">
        <div className="cw-pbar-top">
          <Link href="/projects" className="cw-pbar-back">‹ 项目</Link>
          {editing ? (
            <Input
              autoFocus
              size="small"
              value={title}
              maxLength={120}
              onChange={(e) => setTitle(e.target.value)}
              onBlur={saveTitle}
              onPressEnter={saveTitle}
              style={{ maxWidth: 520 }}
              aria-label="项目标题"
            />
          ) : (
            <h1 className="cw-pbar-title" title={project.title}>
              {project.title}
              <button type="button" className="cw-link-btn" aria-label="改标题" onClick={() => { setTitle(project.title); setEditing(true); }}>
                <Pencil size={13} />
              </button>
            </h1>
          )}
          <StatusMark project={project} unsaved={unsaved} />
          <span className="cw-grow" />
          <Pipeline />
          <FeishuButton type="project" id={project.id} className="cw-pbar-link" />
          <Link className="cw-pbar-link" href={`/runs?project=${project.id}`}>
            过程
          </Link>
          {project.running_tasks ? <span className="cw-pbar-link cw-num">任务 {project.running_tasks}</span> : null}
        </div>
        <nav className="cw-steps cw-steps-path" aria-label="项目步骤">
          <SignalPath
            steps={steps.map((st, i) => {
              const reached = STAGE_ORDER.indexOf(project.stage === 'outputs' ? 'outputs' : project.stage === 'draft' ? 'draft' : 'idea');
              return {
                key: st.id,
                label: `${i + 1} ${STAGE_LABEL[st.id]}`,
                state: step === st.id ? 'current' : i < reached || (i <= reached && step !== st.id) ? 'done' : 'todo',
                href: st.disabled ? undefined : st.href,
                hint: st.disabled,
              };
            })}
          />
        </nav>
      </header>
      <div className="cw-project-body">{children}</div>
    </div>
  );
}

// ── 灵感库选择器 ──

export function libraryThumb(item: { id: number; thumb: boolean; cover_url?: string | null }): string | null {
  return item.thumb ? libraryFileUrl(item.id, 'small') : item.cover_url || null;
}

const PICK_KINDS = [
  { value: '', label: '全部' },
  { value: 'image', label: '图片' },
  { value: 'style', label: '风格' },
  { value: 'prompt', label: '提示词' },
  { value: 'note', label: '随笔' },
  { value: 'video', label: '视频' },
  { value: 'article', label: '文章' },
];

export function AssetPicker({
  open,
  onClose,
  onPick,
  title = '从灵感库添加',
  multiple = true,
  exclude = [],
}: {
  open: boolean;
  onClose: () => void;
  onPick: (items: LibraryItem[]) => void | Promise<void>;
  title?: string;
  multiple?: boolean;
  exclude?: number[];
}) {
  const [q, setQ] = useState('');
  const [kind, setKind] = useState('');
  const [items, setItems] = useState<LibraryItem[]>([]);
  const [picked, setPicked] = useState<LibraryItem[]>([]);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    if (!open) return;
    const t = setTimeout(async () => {
      setLoading(true);
      try {
        const kindParam = ['image', 'video'].includes(kind) ? { asset_kind: kind } : kind ? { kind } : {};
        const r = await libraryApi.list({ q: q || undefined, limit: 60, ...kindParam });
        setItems(r.items);
      } catch (err) {
        message.error(apiError(err, '灵感库加载失败'));
      } finally {
        setLoading(false);
      }
    }, 300);
    return () => clearTimeout(t);
  }, [open, q, kind]);
  const toggle = (it: LibraryItem) =>
    setPicked((v) => (v.some((x) => x.id === it.id) ? v.filter((x) => x.id !== it.id) : multiple ? [...v, it] : [it]));
  const done = async () => {
    await onPick(picked);
    setPicked([]);
    onClose();
  };
  return (
    <Modal open={open} onCancel={onClose} title={title} width={860} onOk={done} okText={`添加${picked.length ? ` ${picked.length} 项` : ''}`} okButtonProps={{ disabled: !picked.length }} destroyOnHidden>
      <div className="cw-row" style={{ marginBottom: 10 }}>
        <SearchField placeholder="搜索标题、描述、标签" value={q} onChange={setQ} />
        <div className="cw-seg" role="group" aria-label="类型">
          {PICK_KINDS.map((k) => (
            <button key={k.value} type="button" aria-pressed={kind === k.value} onClick={() => setKind(k.value)}>
              {k.label}
            </button>
          ))}
        </div>
      </div>
      <div className="cw-pickgrid" aria-busy={loading}>
        {items.filter((i) => !exclude.includes(i.id)).map((it) => {
          const on = picked.some((x) => x.id === it.id);
          const img = libraryThumb(it);
          return (
            <button key={it.id} type="button" className="cw-picktile" aria-pressed={on} onClick={() => toggle(it)} title={it.title}>
              {img ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={img} alt="" loading="lazy" />
              ) : (
                <span className="cw-picktile-text" style={{ background: it.dominant_color || undefined }}>
                  {it.body?.slice(0, 60) || it.title}
                </span>
              )}
              <span className="cw-picktile-cap">
                <em>{PICK_KINDS.find((k) => k.value === (it.asset_kind || it.kind))?.label || it.kind}</em> {it.title}
              </span>
            </button>
          );
        })}
        {!loading && !items.length ? <div className="cw-empty">灵感库里没有匹配的条目</div> : null}
      </div>
    </Modal>
  );
}

// ── 来源选择器 ──

type PickerTab = 'library' | 'today' | 'manual';

interface Candidate {
  key: string;
  content_id?: number;
  library_item_id?: number;
  title: string;
  platform: string | null;
  author: string | null;
  cover: string | null;
  color: string | null;
  orientation: 'landscape' | 'portrait' | null;
  kind: string;
  metric: string | null;
  summary: string | null;
  url: string | null;
}

function fromCard(c: ItemCard): Candidate {
  return {
    key: `content:${c.id}`,
    content_id: c.id,
    title: c.title,
    platform: c.platform,
    author: c.author,
    cover: c.cover_asset_id ? mediaUrl(c.cover_asset_id) : c.cover_url,
    color: c.cover_color,
    orientation: c.orientation,
    kind: c.media_type,
    metric: c.metric?.metric && c.metric.value != null ? `${METRIC_LABEL[c.metric.metric] || c.metric.metric} ${compactNumber(c.metric.value)}` : null,
    summary: c.summary,
    url: c.url,
  };
}

function fromLibrary(it: LibraryItem): Candidate {
  return {
    key: `library:${it.id}`,
    library_item_id: it.id,
    title: it.title,
    platform: it.platform,
    author: it.author,
    cover: libraryThumb(it),
    color: it.dominant_color,
    orientation: it.height && it.width && it.height > it.width ? 'portrait' : 'landscape',
    kind: it.asset_kind || it.kind,
    metric: null,
    summary: it.ai_description || it.body,
    url: it.url || it.source_url,
  };
}

export function SourcePicker({
  project,
  onChanged,
  onManual,
}: {
  project: ProjectView;
  onChanged: () => void;
  onManual: (theme: string) => void;
}) {
  const [tab, setTab] = useState<PickerTab>('library');
  const [q, setQ] = useState('');
  const [items, setItems] = useState<Candidate[]>([]);
  const [selected, setSelected] = useState<Candidate | null>(null);
  const [loading, setLoading] = useState(false);
  const [manual, setManual] = useState('');
  const chosen = new Set(project.sources.map((s) => s.ref));
  useEffect(() => {
    if (tab === 'manual') return;
    const t = setTimeout(async () => {
      setLoading(true);
      try {
        if (tab === 'library') {
          const r = await libraryApi.list({ q: q || undefined, limit: 30 });
          setItems(r.items.filter((i) => !['style', 'prompt', 'note'].includes(i.kind)).map(fromLibrary));
        } else {
          const r = await discoverApi.feed({ view: 'all', limit: 30 });
          const ql = q.trim().toLowerCase();
          setItems(r.items.filter((c) => !ql || c.title.toLowerCase().includes(ql)).map(fromCard));
        }
      } catch (err) {
        message.error(apiError(err, '列表加载失败'));
      } finally {
        setLoading(false);
      }
    }, 300);
    return () => clearTimeout(t);
  }, [tab, q]);
  const add = async (c: Candidate, role: 'main' | 'reference') => {
    try {
      await projectsApi.addSource(project.id, { content_id: c.content_id, library_item_id: c.library_item_id, role });
      onChanged();
    } catch (err) {
      message.error(apiError(err));
    }
  };
  return (
    <div className="cw-picker">
      <section className="cw-picker-list">
        <div className="cw-tabs" role="tablist" style={{ marginBottom: 10 }}>
          {(
            [
              ['library', '灵感库'],
              ['today', '今日'],
              ['manual', '手动输入'],
            ] as const
          ).map(([id, label]) => (
            <button key={id} type="button" role="tab" aria-selected={tab === id} onClick={() => setTab(id)}>
              {label}
            </button>
          ))}
        </div>
        {tab === 'manual' ? (
          <div className="cw-form">
            <label>
              主题
              <Input.TextArea value={manual} onChange={(e) => setManual(e.target.value)} autoSize={{ minRows: 3, maxRows: 6 }} maxLength={500} placeholder="直接写下想做的主题" />
            </label>
            <div>
              <Button variant="primary" disabled={!manual.trim()} onClick={() => onManual(manual.trim())}>
                用作主题
              </Button>
            </div>
          </div>
        ) : (
          <>
            <SearchField placeholder="搜索" width="100%" value={q} onChange={setQ} />
            <ul className="cw-cands" aria-busy={loading}>
              {items.map((c) => (
                <li key={c.key}>
                  <button type="button" className="cw-cand" aria-pressed={selected?.key === c.key} onClick={() => setSelected(c)}>
                    <Cover src={c.cover} title={c.title} color={c.color} orientation={c.orientation} kind={c.kind} />
                    <span className="cw-cand-main">
                      <span className="cw-cand-title">{c.title}</span>
                      <span className="cw-cand-meta">
                        {platformName(c.platform)} {c.author ? `· ${c.author}` : ''} {c.metric ? <em className="cw-num">{c.metric}</em> : null}
                      </span>
                    </span>
                    {chosen.has(c.key) ? <span className="cw-ok" aria-label="已选">✓</span> : null}
                  </button>
                </li>
              ))}
              {!loading && !items.length ? <li className="cw-empty">没有条目</li> : null}
            </ul>
          </>
        )}
      </section>
      <section className="cw-picker-detail">
        {selected ? (
          <>
            <div className="cw-picker-cover">
              <Cover src={selected.cover} title={selected.title} color={selected.color} orientation={selected.orientation} kind={selected.kind} />
            </div>
            <h3 className="cw-picker-title">{selected.title}</h3>
            <p className="cw-muted">
              {platformName(selected.platform)} {selected.author ? `· ${selected.author}` : ''}{' '}
              {selected.url ? (
                <a href={selected.url} target="_blank" rel="noreferrer">
                  原文 ↗
                </a>
              ) : null}
            </p>
            {selected.metric ? <p className="cw-num">{selected.metric}</p> : null}
            {selected.summary ? <p className="cw-picker-summary">{selected.summary.slice(0, 600)}</p> : null}
            <div className="cw-row">
              <Button variant="primary" onClick={() => add(selected, 'main')} disabled={project.sources.some((s) => s.ref === selected.key && s.role === 'main')}>
                设为主来源
              </Button>
              <Button onClick={() => add(selected, 'reference')} disabled={chosen.has(selected.key)}>
                加为参考
              </Button>
              {selected.content_id ? (
                <Link className="cw-btn" data-variant="ghost" href={`/items/${selected.content_id}`} target="_blank">
                  完整详情
                </Link>
              ) : null}
            </div>
          </>
        ) : (
          <div className="cw-empty">从左侧挑一条看详情</div>
        )}
      </section>
    </div>
  );
}

export function SelectedSources({ project, onChanged }: { project: ProjectView; onChanged: () => void }) {
  const act = async (fn: () => Promise<unknown>) => {
    try {
      await fn();
      onChanged();
    } catch (err) {
      message.error(apiError(err));
    }
  };
  if (!project.sources.length) return <span className="cw-muted">还没有来源。可以先挑一条，也可以直接写主题。</span>;
  return (
    <div className="cw-chips">
      {project.sources.map((s: ProjectSource) => (
        <span key={s.id} className="cw-srcchip" data-main={s.role === 'main' || undefined}>
          {s.role === 'main' ? '★ ' : ''}
          <span className="cw-srcchip-title" title={s.snapshot.title || ''}>{s.snapshot.title || s.ref}</span>
          <small>{s.role === 'main' ? '主来源' : '参考'}</small>
          {s.role !== 'main' ? (
            <button type="button" className="cw-link-btn" onClick={() => act(() => projectsApi.setSourceRole(project.id, s.id, 'main'))}>
              设为主
            </button>
          ) : null}
          <button type="button" className="cw-link-btn" aria-label="移除" onClick={() => act(() => projectsApi.removeSource(project.id, s.id))}>
            ✕
          </button>
        </span>
      ))}
    </div>
  );
}

// ── 情绪板 ──

export function MoodBoard({ projectId }: { projectId: number }) {
  const [assets, setAssets] = useState<ProjectAsset[]>([]);
  const [open, setOpen] = useState(false);
  const [genOpen, setGenOpen] = useState(false);
  const load = useCallback(async () => {
    try {
      setAssets((await projectsApi.assets(projectId, 'moodboard')).items);
    } catch (err) {
      message.error(apiError(err, '情绪板加载失败'));
    }
  }, [projectId]);
  useEffect(() => {
    void load();
  }, [load]);
  const add = async (items: LibraryItem[]) => {
    for (const it of items) {
      try {
        await projectsApi.addAsset(projectId, it.id, 'moodboard');
      } catch (err) {
        message.error(apiError(err));
        break;
      }
    }
    await load();
  };
  const remove = async (aid: number) => {
    await projectsApi.removeAsset(projectId, aid);
    await load();
  };
  return (
    <>
      <div className="cw-mood">
        {assets.map((a) => {
          const it = a.item;
          const img = it?.thumb ? libraryFileUrl(it.id, 'small') : null;
          return (
            <figure key={a.id} className="cw-mood-tile" title={it?.title}>
              {img ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={img} alt="" loading="lazy" />
              ) : (
                <span className="cw-mood-text" style={{ background: it?.color || undefined } as CSSProperties}>
                  {it?.body || it?.title || '已删除'}
                </span>
              )}
              <figcaption>
                <span>{it?.title}</span>
                <button type="button" className="cw-link-btn" aria-label="移出情绪板" onClick={() => remove(a.id)}>
                  ✕
                </button>
              </figcaption>
            </figure>
          );
        })}
        <button type="button" className="cw-mood-add" onClick={() => setOpen(true)}>
          + 从灵感库添加
        </button>
        <button type="button" className="cw-mood-add" onClick={() => setGenOpen(true)}>
          + 生图
        </button>
      </div>
      <AssetPicker open={open} onClose={() => setOpen(false)} onPick={add} exclude={assets.map((a) => a.library_item_id)} />
      <ImageGenPanel
        open={genOpen}
        onClose={() => setGenOpen(false)}
        projectId={projectId}
        target={{ type: 'moodboard' }}
        defaultRefIds={assets.filter((a) => a.item?.thumb).map((a) => a.library_item_id).slice(0, 4)}
        onKept={() => void load()}
      />
    </>
  );
}

// ── 方向卡（选题研究流程产物）──

export interface DirectionCardView {
  id: string;
  title: string;
  angle: string;
  why_now?: string;
  format?: string | null;
  refs?: string[];
}

export function useDirectionRun(runId: number | undefined) {
  const [state, setState] = useState<{ status: string; reason: string | null; cards: DirectionCardView[] } | null>(null);
  useEffect(() => {
    if (!runId) {
      setState(null);
      return;
    }
    let stop = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const tick = async () => {
      try {
        const d = await runsApi.get(runId);
        const art = [...d.artifacts].reverse().find((a) => a.kind === 'direction_cards');
        const cards = (art?.content?.cards as DirectionCardView[] | undefined) || [];
        if (!stop) setState({ status: d.run.status, reason: d.run.status_reason, cards });
        if (!stop && ['running', 'queued'].includes(d.run.status)) timer = setTimeout(tick, 2500);
      } catch {
        if (!stop) timer = setTimeout(tick, 5000);
      }
    };
    void tick();
    return () => {
      stop = true;
      if (timer) clearTimeout(timer);
    };
  }, [runId]);
  return state;
}


// ── 流程运行：轮询 + 阶段条（成稿 / 成片）──

/** 运行中每 2 秒刷新一次；结束时回调一次。 */
export function useRunWatch(runId: number | undefined | null, onFinish?: (d: RunDetail) => void) {
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const finishRef = useRef(onFinish);
  useEffect(() => {
    finishRef.current = onFinish;
  }, [onFinish]);
  useEffect(() => {
    if (!runId) {
      setDetail(null);
      return;
    }
    let stop = false;
    let wasActive = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const tick = async () => {
      try {
        const d = await runsApi.get(runId);
        if (stop) return;
        setDetail(d);
        const active = ACTIVE_RUN.includes(d.run.status) && d.run.status !== 'waiting';
        if (active) {
          wasActive = true;
          timer = setTimeout(tick, 2000);
        } else if (d.run.status === 'waiting') {
          timer = setTimeout(tick, 5000);
        } else if (wasActive) {
          finishRef.current?.(d);
        }
      } catch {
        if (!stop) timer = setTimeout(tick, 5000);
      }
    };
    void tick();
    return () => {
      stop = true;
      if (timer) clearTimeout(timer);
    };
  }, [runId]);
  return detail;
}

const STAGE_COLOR: Record<FlowStage['status'], string> = {
  pending: color.dim,
  running: color.cy,
  waiting: color.yl,
  done: color.gr,
  reused: color.bl,
  failed: color.rd,
  stopped: color.dim,
};
const STAGE_TEXT: Record<FlowStage['status'], string> = {
  pending: '等待',
  running: '进行中',
  waiting: '等你处理',
  done: '完成',
  reused: '复用',
  failed: '失败',
  stopped: '已停止',
};

export function RunStages({ detail, compact = false }: { detail: RunDetail; compact?: boolean }) {
  const stages = flowStages(detail.graph, detail.steps);
  return (
    <div className="cw-runstages" aria-live="polite">
      <ol>
        {stages.map((s) => (
          <li key={s.id} data-status={s.status} data-gate={s.type === 'gate' || undefined} title={s.error || s.summary || undefined}>
            <span className="cw-runstage-dot" style={{ background: STAGE_COLOR[s.status] }} />
            <b>{s.label}</b>
            <small style={{ color: STAGE_COLOR[s.status] }}>
              {STAGE_TEXT[s.status]}
              {s.rounds > 1 ? ` · 第 ${s.round} 轮` : ''}
            </small>
            {!compact && s.summary ? <em>{s.summary}</em> : null}
          </li>
        ))}
      </ol>
      <div className="cw-runstages-foot">
        <span className="cw-num">¥{detail.run.cost.toFixed(2)}</span>
        {detail.run.status_reason ? <span className="cw-muted">{detail.run.status_reason}</span> : null}
        <span className="cw-grow" />
        <Link className="cw-link-btn" href={`/runs/${detail.run.id}`}>
          查看过程
        </Link>
      </div>
    </div>
  );
}
