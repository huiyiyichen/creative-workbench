'use client';

/** 项目（设计文档 2 节 + 设计评审 #1 · 2.6）：看板按步骤分三栏（选题中 / 写稿中 / 产出），也可切列表；新建、复制、批量归档。 */

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Input } from 'antd';
import { Copy, Plus } from 'lucide-react';
import { useCallback, useEffect, useState, type CSSProperties } from 'react';
import { Button, Chip, Cover, CwPage, SearchField, Segmented, TopBar } from '@/design/components';
import { confirmAction, toast } from '@/design/feedback';
import { EmptyInstrument, ScanSkeleton, SignalPath } from '@/design/instrument';
import { MODE_COLOR, MODE_LABEL, STAGE_LABEL, apiError } from '@/design/studio';
import { relativeTime } from '@/lib/collection';
import { projectsApi, type ProjectMode, type ProjectStage, type ProjectSummary } from '@/lib/api/_projects';

const STAGES: ProjectStage[] = ['idea', 'draft', 'outputs'];
const COLUMN_LABEL: Record<ProjectStage, string> = { idea: '选题中', draft: '写稿中', outputs: '产出' };
const MODES: { value: ProjectMode; label: string }[] = [
  { value: 'article', label: '图文 / 文章' },
  { value: 'animation_video', label: '动画讲解' },
  { value: 'video_prompt', label: '视频提示词' },
  { value: 'music_video', label: '音乐 MV' },
];

function stepOf(p: ProjectSummary): ProjectStage {
  return p.stage === 'outputs' ? 'outputs' : p.stage === 'draft' ? 'draft' : 'idea';
}

function MiniPath({ p }: { p: ProjectSummary }) {
  const at = STAGES.indexOf(stepOf(p));
  return (
    <SignalPath
      steps={STAGES.map((s, i) => ({ key: s, label: STAGE_LABEL[s].slice(0, 2), state: i < at ? 'done' : i === at ? 'current' : 'todo' }))}
    />
  );
}

function ProjectCard({
  p,
  picked,
  onPick,
  onDuplicate,
  onArchive,
}: {
  p: ProjectSummary;
  picked: boolean;
  onPick: () => void;
  onDuplicate: () => void;
  onArchive: () => void;
}) {
  const href = `/projects/${p.id}/${stepOf(p)}`;
  return (
    <article className="cw-pcard" data-picked={picked ? 'true' : undefined} data-art-host style={{ '--c': MODE_COLOR[p.mode] } as CSSProperties}>
      <Link href={href} className="cw-pcard-cover" tabIndex={-1} aria-hidden>
        <Cover src={p.main_source?.cover_url || null} title={p.title} kind={p.mode === 'article' ? 'article' : 'video'} />
      </Link>
      <div className="cw-pcard-body">
        <Link href={href} className="cw-pcard-title">
          {p.title}
        </Link>
        <div className="cw-pcard-meta">
          <span className="cw-pcard-mode">
            <i />
            {MODE_LABEL[p.mode]}
          </span>
          <span className="cw-num">{p.finalized_version ? `定稿 v${p.finalized_version}` : p.version ? `草稿 v${p.version}` : '未成稿'}</span>
          {p.outputs ? <span className="cw-num">{p.outputs} 个产出</span> : null}
        </div>
        <MiniPath p={p} />
        <footer>
          <span className="cw-num cw-muted">{relativeTime(p.updated_at)}更新</span>
          <span className="cw-grow" />
          <span className="cw-pcard-acts">
          <button type="button" className="cw-icon-btn" title="复制为新项目（带设定、文稿、来源、素材）" aria-label="复制" onClick={onDuplicate}>
            <Copy size={13} />
          </button>
          <button type="button" className="cw-link-btn" onClick={onArchive}>
            {p.archived ? '恢复' : '归档'}
          </button>
          <input type="checkbox" className="cw-check" checked={picked} onChange={onPick} aria-label={`选择 ${p.title}`} />
          </span>
        </footer>
      </div>
    </article>
  );
}

function CreateCard({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const [theme, setTheme] = useState('');
  const [mode, setMode] = useState<ProjectMode>('article');
  const [busy, setBusy] = useState(false);
  const create = async () => {
    setBusy(true);
    try {
      const p = await projectsApi.create({ theme: theme.trim(), mode });
      router.push(`/projects/${p.id}/idea`);
    } catch (err) {
      toast.error(apiError(err, '新建失败'));
      setBusy(false);
    }
  };
  return (
    <section className="cw-instrument cw-pcreate" aria-label="新建项目">
      <Input
        autoFocus
        size="large"
        placeholder="这个项目讲什么？一句话主题，可以先空着"
        value={theme}
        onChange={(e) => setTheme(e.target.value)}
        onPressEnter={create}
        maxLength={500}
      />
      <div className="cw-row" style={{ flexWrap: 'wrap', gap: 8 }}>
        {MODES.map((m) => (
          <button key={m.value} type="button" className="cw-chip cw-toggle" aria-pressed={mode === m.value} onClick={() => setMode(m.value)}>
            <b />
            {m.label}
          </button>
        ))}
        <span className="cw-grow" />
        <Link className="cw-link-btn" href="/library">
          从灵感库挑一条
        </Link>
        <Link className="cw-link-btn" href="/">
          从今日挑一条
        </Link>
        <Button variant="ghost" onClick={onClose}>
          取消
        </Button>
        <Button variant="primary" onClick={create} disabled={busy}>
          {busy ? '创建中…' : '新建'}
        </Button>
      </div>
    </section>
  );
}

export default function ProjectsPage() {
  const router = useRouter();
  const [view, setView] = useState<'board' | 'list'>('board');
  const [archived, setArchived] = useState(false);
  const [q, setQ] = useState('');
  const [items, setItems] = useState<ProjectSummary[] | null>(null);
  const [creating, setCreating] = useState(false);
  const [picked, setPicked] = useState<Set<number>>(new Set());

  const load = useCallback(async () => {
    try {
      const r = await projectsApi.list({ archived, q: q || undefined });
      setItems(r.items);
    } catch (err) {
      toast.error(apiError(err, '项目加载失败'));
      setItems([]);
    }
  }, [archived, q]);
  useEffect(() => {
    const t = setTimeout(load, 250);
    return () => clearTimeout(t);
  }, [load]);

  const toggle = (id: number) =>
    setPicked((cur) => {
      const next = new Set(cur);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const duplicate = async (p: ProjectSummary) => {
    try {
      const c = await projectsApi.duplicate(p.id);
      router.push(`/projects/${c.id}/idea`);
    } catch (err) {
      toast.error(err, '复制失败');
    }
  };
  const archive = async (p: ProjectSummary) => {
    await projectsApi.archive(p.id, p.archived);
    await load();
  };
  const batch = async (action: 'archive' | 'unarchive' | 'delete') => {
    const ids = [...picked];
    if (
      action === 'delete' &&
      !(await confirmAction({ title: `删除 ${ids.length} 个已归档项目？`, content: '文稿、版本和产出物都会一起删除，不能恢复。', okText: '删除', danger: true }))
    )
      return;
    try {
      const r = await projectsApi.batch(ids, action);
      toast.success(r.skipped.length ? `已处理 ${r.done} 个；${r.skipped.length} 个没归档的没删` : `已处理 ${r.done} 个`);
      setPicked(new Set());
      await load();
    } catch (err) {
      toast.error(err, '批量操作失败');
    }
  };

  const by = (s: ProjectStage) => (items || []).filter((p) => stepOf(p) === s);
  const active = items?.length ?? 0;
  const sub = items ? (archived ? `${active} 个已归档` : `${active} 个进行中 · ${by('outputs').length} 个在产出`) : undefined;

  return (
    <CwPage>
      <TopBar title="项目" sub={sub ? <span className="cw-num">{sub}</span> : undefined}>
        <Segmented
          label="视图"
          value={view}
          onChange={setView}
          options={[
            { value: 'board', label: '看板' },
            { value: 'list', label: '列表' },
          ]}
        />
        <Button variant="primary" icon={<Plus size={15} />} onClick={() => setCreating(true)}>
          新建项目
        </Button>
      </TopBar>
      {creating ? <CreateCard onClose={() => setCreating(false)} /> : null}
      <div className="cw-filters">
        <SearchField placeholder="搜索项目" width={240} value={q} onChange={setQ} />
        <button type="button" className="cw-chip cw-toggle" aria-pressed={archived} onClick={() => setArchived((v) => !v)}>
          <b />
          已归档
        </button>
        {picked.size ? (
          <div className="cw-row cw-batchbar" role="toolbar" aria-label="批量操作">
            <span className="cw-num">已选 {picked.size}</span>
            {archived ? (
              <>
                <Button onClick={() => batch('unarchive')}>恢复</Button>
                <Button variant="ghost" onClick={() => batch('delete')}>
                  删除
                </Button>
              </>
            ) : (
              <Button onClick={() => batch('archive')}>归档</Button>
            )}
            <Button variant="ghost" onClick={() => setPicked(new Set())}>
              取消
            </Button>
          </div>
        ) : null}
      </div>
      {items === null ? (
        <ScanSkeleton height={320} />
      ) : items.length === 0 ? (
        archived || q ? (
          <EmptyInstrument kind="dark" title={q ? `没有标题含「${q}」的项目` : '没有已归档的项目'} />
        ) : (
          <EmptyInstrument
            kind="flat"
            title="还没有项目"
            reason="项目从一个主题、或今日 / 灵感库里的一条内容开始：选题 → 写稿 → 做成各平台版本和视频。"
            actions={
              <>
                <Button variant="primary" icon={<Plus size={15} />} onClick={() => setCreating(true)}>
                  新建项目
                </Button>
                <Link className="cw-link-btn" href="/">
                  从今日挑一条
                </Link>
                <Link className="cw-link-btn" href="/library">
                  从灵感库挑
                </Link>
              </>
            }
          />
        )
      ) : view === 'board' && !archived ? (
        <div className="cw-board" data-picking={picked.size ? "true" : undefined}>
          {STAGES.map((s) => (
            <section key={s} className="cw-board-col" aria-label={COLUMN_LABEL[s]}>
              <header>
                <h2>{COLUMN_LABEL[s]}</h2>
                <span className="cw-num cw-muted">{by(s).length}</span>
              </header>
              <div className="cw-board-cards cw-stagger">
                {by(s).length ? (
                  by(s).map((p) => (
                    <ProjectCard
                      key={p.id}
                      p={p}
                      picked={picked.has(p.id)}
                      onPick={() => toggle(p.id)}
                      onDuplicate={() => duplicate(p)}
                      onArchive={() => archive(p)}
                    />
                  ))
                ) : (
                  <p className="cw-board-empty">{s === 'idea' ? '新建的项目从这里开始' : s === 'draft' ? '选定方向后进入写稿' : '定稿后在这里做各平台版本'}</p>
                )}
              </div>
            </section>
          ))}
        </div>
      ) : (
        <ul className="cw-plist cw-stagger">
          {items.map((p) => {
            const step = stepOf(p);
            return (
              <li key={p.id} className="cw-plist-row" data-picked={picked.has(p.id) ? 'true' : undefined}>
                <input type="checkbox" className="cw-check" checked={picked.has(p.id)} onChange={() => toggle(p.id)} aria-label={`选择 ${p.title}`} />
                <Link href={`/projects/${p.id}/${step}`} className="cw-plist-cover" aria-hidden tabIndex={-1}>
                  <Cover src={p.main_source?.cover_url || null} title={p.title} kind={p.mode === 'article' ? 'article' : 'video'} />
                </Link>
                <div className="cw-plist-main">
                  <Link href={`/projects/${p.id}/${step}`} className="cw-plist-title">
                    {p.title}
                  </Link>
                  <span className="cw-muted">
                    {p.main_source?.title ? `来源：${p.main_source.title}` : '无来源'} · 更新于 {relativeTime(p.updated_at)}
                  </span>
                </div>
                <Chip color={MODE_COLOR[p.mode]}>{MODE_LABEL[p.mode]}</Chip>
                <MiniPath p={p} />
                <span className={p.status === 'finalized' ? 'cw-pstatus' : 'cw-muted'} data-tone={p.status === 'finalized' ? 'final' : undefined}>
                  {p.finalized_version ? `已定稿 v${p.finalized_version}` : p.version ? `草稿 v${p.version}` : '草稿'}
                </span>
                <span className="cw-num cw-muted">{p.outputs ? `${p.outputs} 个产出` : ''}</span>
                <button type="button" className="cw-link-btn" onClick={() => duplicate(p)} title="复制设定、文稿、来源和素材，当模板用">
                  复制
                </button>
                <button type="button" className="cw-link-btn" onClick={() => archive(p)}>
                  {p.archived ? '恢复' : '归档'}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </CwPage>
  );
}
