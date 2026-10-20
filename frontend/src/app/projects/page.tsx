'use client';

/** 项目列表（设计文档 2 节）：按步骤筛选、搜索、新建、归档。 */

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Input, message } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import { confirmAction, toast } from '@/design/feedback';
import { Button, Chip, Cover, CwPage, Segmented, TopBar } from '@/design/components';
import { MODE_COLOR, MODE_LABEL, STAGE_LABEL, apiError } from '@/design/studio';
import { relativeTime } from '@/lib/collection';
import { projectsApi, type ProjectStage, type ProjectSummary } from '@/lib/api/_projects';

const FILTERS = [
  { value: '', label: '全部' },
  { value: 'idea', label: '选题中' },
  { value: 'draft', label: '写稿中' },
  { value: 'outputs', label: '产出' },
  { value: 'archived', label: '已归档' },
] as const;
type Filter = (typeof FILTERS)[number]['value'];

export default function ProjectsPage() {
  const router = useRouter();
  const [filter, setFilter] = useState<Filter>('');
  const [q, setQ] = useState('');
  const [items, setItems] = useState<ProjectSummary[] | null>(null);
  const [theme, setTheme] = useState('');
  const load = useCallback(async () => {
    try {
      const r = await projectsApi.list({
        stage: filter && filter !== 'archived' ? (filter as ProjectStage) : undefined,
        archived: filter === 'archived',
        q: q || undefined,
      });
      setItems(r.items);
    } catch (err) {
      message.error(apiError(err, '项目加载失败'));
      setItems([]);
    }
  }, [filter, q]);
  useEffect(() => {
    const t = setTimeout(load, 250);
    return () => clearTimeout(t);
  }, [load]);
  const create = async () => {
    try {
      const p = await projectsApi.create({ theme: theme.trim() });
      router.push(`/projects/${p.id}/idea`);
    } catch (err) {
      message.error(apiError(err, '新建失败'));
    }
  };
  const archive = async (p: ProjectSummary) => {
    await projectsApi.archive(p.id, p.archived);
    await load();
  };
  const [picked, setPicked] = useState<Set<number>>(new Set());
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
  const batch = async (action: 'archive' | 'unarchive' | 'delete') => {
    const ids = [...picked];
    if (action === 'delete' && !(await confirmAction({ title: `删除 ${ids.length} 个已归档项目？`, content: '文稿、版本和产出物都会一起删除，不能恢复。', okText: '删除', danger: true }))) return;
    try {
      const r = await projectsApi.batch(ids, action);
      toast.success(r.skipped.length ? `已处理 ${r.done} 个；${r.skipped.length} 个没归档的没删` : `已处理 ${r.done} 个`);
      setPicked(new Set());
      await load();
    } catch (err) {
      toast.error(err, '批量操作失败');
    }
  };
  return (
    <CwPage>
      <TopBar title="项目" sub={items ? `${items.length} 个` : undefined}>
        <Input
          placeholder="新项目的主题（可留空，之后从灵感库挑）"
          value={theme}
          onChange={(e) => setTheme(e.target.value)}
          onPressEnter={create}
          style={{ width: 320 }}
          maxLength={500}
        />
        <Button variant="primary" onClick={create}>
          新建项目
        </Button>
      </TopBar>
      <div className="cw-filters">
        <Segmented value={filter} options={FILTERS.map((f) => ({ value: f.value, label: f.label }))} onChange={setFilter} label="步骤" />
        <Input.Search allowClear placeholder="搜索标题" value={q} onChange={(e) => setQ(e.target.value)} style={{ width: 240 }} />
        {picked.size ? (
          <div className="cw-row cw-batchbar" role="toolbar" aria-label="批量操作">
            <span className="cw-num">已选 {picked.size}</span>
            {filter === 'archived' ? (
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
        <div className="cw-empty">加载中…</div>
      ) : items.length ? (
        <ul className="cw-plist">
          {items.map((p) => {
            const step = p.stage === 'outputs' ? 'outputs' : p.stage === 'draft' ? 'draft' : 'idea';
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
                <span className="cw-muted">{STAGE_LABEL[p.stage]}</span>
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
      ) : (
        <div className="cw-empty" data-block="true">还没有项目。写个主题新建，或在今日 / 灵感库里点「做成项目」。</div>
      )}
    </CwPage>
  );
}
