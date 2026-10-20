'use client';

/**
 * 灵感库（改造方案 6）：瀑布流画廊（素材默认）/ 列表；形态、素材类型、授权、标签、颜色、画板筛选；
 * 粘贴链接、拖入文件、粘贴截图收进来；多选改授权、加画板、提炼为风格 / 模板。图谱在独立页签。
 */

import { parseUTC } from '@/lib/datetime';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { Input, Select, message } from 'antd';
import { CheckSquare, Plus, Sparkles } from 'lucide-react';
import { Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import { Button, Card, CwPage, Segmented, TopBar } from '@/design/components';
import {
  ASSET_LABEL,
  KIND_LABEL,
  LICENSE_LABEL,
  libraryApi,
  type Board,
  type LibraryFacets,
  type LibraryItem,
  type License,
} from '@/lib/api/_library';
import { AddBar, LibraryCard, LibraryDrawer, useDropAndPaste } from './_parts';

const KIND_TABS = [
  { value: '', label: '全部' },
  { value: 'asset', label: '素材' },
  { value: 'video', label: '视频' },
  { value: 'article', label: '文章' },
  { value: 'image', label: '图文' },
  { value: 'prompt', label: '提示词' },
  { value: 'repo', label: '仓库' },
  { value: 'generated', label: '生成图' },
  { value: 'link', label: '链接' },
];

function errText(err: unknown): string {
  return err instanceof Error ? err.message : '请求失败';
}

function fmtBytes(n: number): string {
  if (n > 1e9) return `${(n / 1e9).toFixed(1)} GB`;
  if (n > 1e6) return `${(n / 1e6).toFixed(1)} MB`;
  return `${Math.round(n / 1e3)} KB`;
}

function LibraryPage() {
  const router = useRouter();
  const params = useSearchParams();
  const kind = params.get('kind') || '';
  const boardId = params.get('board') ? Number(params.get('board')) : undefined;
  const [view, setView] = useState<'gallery' | 'list'>('gallery');
  const [assetKind, setAssetKind] = useState<string | undefined>();
  const [license, setLicense] = useState<string | undefined>();
  const [tag, setTag] = useState<string | undefined>();
  const [q, setQ] = useState('');
  const [colorQ, setColorQ] = useState<string | undefined>();
  const [items, setItems] = useState<LibraryItem[] | null>(null);
  const [total, setTotal] = useState(0);
  const [facets, setFacets] = useState<LibraryFacets | null>(null);
  const [boards, setBoards] = useState<Board[]>([]);
  const [openId, setOpenId] = useState<number | null>(() => (params.get('open') ? Number(params.get('open')) : null));
  const [selecting, setSelecting] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [newBoard, setNewBoard] = useState('');

  const load = useCallback(async () => {
    try {
      const r = await libraryApi.list({ kind: kind || undefined, asset_kind: assetKind, license, tag, q: q || undefined, color: colorQ, board_id: boardId, limit: 120 });
      setItems(r.items);
      setTotal(r.total);
    } catch (err) {
      message.error(errText(err));
      setItems([]);
    }
  }, [kind, assetKind, license, tag, q, colorQ, boardId]);

  const loadSide = useCallback(() => {
    libraryApi.facets().then(setFacets).catch(() => undefined);
    libraryApi.boards().then((r) => setBoards(r.items)).catch(() => undefined);
  }, []);

  useEffect(() => {
    const t = setTimeout(load, 200);
    return () => clearTimeout(t);
  }, [load]);
  useEffect(() => {
    loadSide();
  }, [loadSide]);
  useEffect(() => {
    if (kind === 'asset' || kind === 'generated') setView('gallery');
  }, [kind]);

  const refresh = useCallback(() => {
    void load();
    loadSide();
  }, [load, loadSide]);

  const onFiles = useCallback(
    async (files: File[], method: 'file' | 'clipboard') => {
      const hide = message.loading(`导入 ${files.length} 个文件…`, 0);
      try {
        const r = await libraryApi.upload(files, method);
        message.success(`导入 ${r.items.length} 个${r.errors.length ? `，${r.errors.length} 个失败` : ''}`);
        refresh();
      } catch (err) {
        message.error(errText(err));
      } finally {
        hide();
      }
    },
    [refresh],
  );
  const onText = useCallback(
    async (text: string) => {
      try {
        const it = /^https?:\/\/\S+$/.test(text) ? await libraryApi.fromLink(text) : await libraryApi.text(text, 'prompt');
        message.success(`已收进：${it.title.slice(0, 30)}`);
        refresh();
      } catch (err) {
        message.error(errText(err));
      }
    },
    [refresh],
  );
  const dragging = useDropAndPaste(onFiles, onText);

  const toggle = (id: number) =>
    setSelected((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });

  const ids = useMemo(() => Array.from(selected), [selected]);
  const bulkLicense = async (lic: License) => {
    await libraryApi.bulkLicense(ids, lic);
    message.success(`已把 ${ids.length} 条改为「${LICENSE_LABEL[lic]}」`);
    refresh();
  };
  const bulkBoard = async (bid: number) => {
    const r = await libraryApi.addToBoard(bid, ids);
    message.success(`加入 ${r.added} 条`);
    refresh();
  };
  const distill = async (k: 'style' | 'template') => {
    const name = window.prompt(k === 'style' ? '风格名称' : '模板名称', tag || '');
    if (!name) return;
    const hide = message.loading('AI 正在读这些素材写规则…', 0);
    try {
      const r = await libraryApi.distill(k, name, ids);
      message.success(`已生成${k === 'style' ? '风格' : '模板'}「${r.name}」，参考 ${r.reference_count} 条`);
      router.push(`/library/styles?${k}=${encodeURIComponent(r.key)}`);
    } catch (err) {
      message.error(errText(err));
    } finally {
      hide();
    }
  };

  const board = boards.find((b) => b.id === boardId);

  return (
    <CwPage>
      <TopBar title="灵感库" sub={board ? `画板 · ${board.name}` : facets ? `${Object.values(facets.kinds).reduce((a, b) => a + b, 0)} 条 · ${fmtBytes(facets.storage.bytes)}` : undefined}>
        <nav className="cw-seg" aria-label="灵感库分页">
          <Link href="/library" aria-current="page">
            收藏
          </Link>
          <Link href="/notes">随笔</Link>
          <Link href="/library/styles">风格与模板</Link>
          <Link href="/library/graph">图谱</Link>
        </nav>
      </TopBar>

      <AddBar onAdded={() => refresh()} />

      <div className="cw-filters">
        <Segmented label="形态" value={kind} onChange={(v) => router.replace(v ? `/library?kind=${v}` : '/library')} options={KIND_TABS} />
        <span className="cw-grow" />
        <Segmented
          label="视图"
          value={view}
          onChange={setView}
          options={[
            { value: 'gallery', label: '画廊' },
            { value: 'list', label: '列表' },
          ]}
        />
      </div>
      <div className="cw-filters">
        <Input.Search allowClear placeholder="搜索标题、正文、标签、AI 描述" style={{ width: 280 }} value={q} onChange={(e) => setQ(e.target.value)} />
        {kind === 'asset' ? (
          <Select
            allowClear
            placeholder="素材类型"
            style={{ width: 120 }}
            value={assetKind}
            onChange={setAssetKind}
            options={Object.entries(ASSET_LABEL).map(([value, label]) => ({ value, label: `${label}${facets?.asset_kinds[value] ? ` ${facets.asset_kinds[value]}` : ''}` }))}
          />
        ) : null}
        <Select allowClear placeholder="授权" style={{ width: 110 }} value={license} onChange={setLicense} options={Object.entries(LICENSE_LABEL).map(([value, label]) => ({ value, label }))} />
        <Select
          allowClear
          showSearch
          placeholder="标签"
          style={{ width: 140 }}
          value={tag}
          onChange={setTag}
          options={(facets?.tags || []).map(([t, n]) => ({ value: t, label: `${t} ${n}` }))}
        />
        <label className="cw-color-pick" title="按颜色找">
          <input type="color" value={colorQ || '#df5bd5'} onChange={(e) => setColorQ(e.target.value)} />
          {colorQ ? (
            <button type="button" className="cw-link-btn" onClick={() => setColorQ(undefined)}>
              清除颜色
            </button>
          ) : (
            <span className="cw-muted">按颜色</span>
          )}
        </label>
        <span className="cw-grow" />
        <span className="cw-muted">{total} 条</span>
        <Button icon={<CheckSquare size={15} />} variant={selecting ? 'primary' : 'default'} onClick={() => { setSelecting(!selecting); setSelected(new Set()); }}>
          {selecting ? '完成' : '多选'}
        </Button>
      </div>

      {selecting && ids.length ? (
        <div className="cw-away" role="toolbar" aria-label="批量操作">
          <span>已选 {ids.length} 条</span>
          <Select size="small" placeholder="改授权" style={{ width: 110 }} value={null} onChange={bulkLicense} options={Object.entries(LICENSE_LABEL).map(([value, label]) => ({ value, label }))} />
          <Select size="small" placeholder="加入画板" style={{ width: 130 }} value={null} onChange={bulkBoard} options={boards.map((b) => ({ value: b.id, label: b.name }))} />
          <Button icon={<Sparkles size={14} />} onClick={() => distill('style')}>
            提炼为风格
          </Button>
          <Button icon={<Sparkles size={14} />} onClick={() => distill('template')}>
            提炼为模板
          </Button>
        </div>
      ) : null}

      <div className="cw-lib-layout">
        <section>
          {dragging ? <div className="cw-lib-drop">松开导入到灵感库</div> : null}
          {!items ? (
            <div className="cw-empty">加载中…</div>
          ) : items.length === 0 ? (
            <div className="cw-empty">还没有东西。粘贴链接、拖进文件，或在任意页面粘贴截图</div>
          ) : view === 'gallery' ? (
            <div className="cw-masonry">
              {items.map((it) => (
                <LibraryCard key={it.id} item={it} onOpen={setOpenId} selecting={selecting} selected={selected.has(it.id)} onToggle={toggle} />
              ))}
            </div>
          ) : (
            <table className="cw-table">
              <thead>
                <tr>
                  <th>标题</th>
                  <th>类型</th>
                  <th>来源</th>
                  <th>授权</th>
                  <th>标签</th>
                  <th>收藏于</th>
                </tr>
              </thead>
              <tbody>
                {items.map((it) => (
                  <tr key={it.id} onClick={() => (selecting ? toggle(it.id) : setOpenId(it.id))} style={{ cursor: 'pointer', background: selected.has(it.id) ? 'var(--cw-raise)' : undefined }}>
                    <td>{it.title}</td>
                    <td>{it.asset_kind ? ASSET_LABEL[it.asset_kind] : KIND_LABEL[it.kind]}</td>
                    <td className="cw-muted">{it.platform || it.author || it.import_method}</td>
                    <td>{LICENSE_LABEL[it.license]}</td>
                    <td className="cw-muted">{it.tags.slice(0, 3).join('、')}</td>
                    <td className="cw-num">{parseUTC(it.created_at).toLocaleDateString('zh-CN')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
        <aside className="cw-today-side">
          <Card title="画板">
            <ul className="cw-report-list">
              <li>
                <Link href={kind ? `/library?kind=${kind}` : '/library'} aria-current={!boardId ? 'page' : undefined}>
                  全部收藏
                </Link>
              </li>
              {boards.map((b) => (
                <li key={b.id}>
                  <Link href={`/library?board=${b.id}`} aria-current={b.id === boardId ? 'page' : undefined}>
                    {b.name}
                  </Link>
                  <span className="cw-grow" />
                  <span className="cw-muted cw-num">{b.count}</span>
                </li>
              ))}
            </ul>
            <div className="cw-filters" style={{ marginTop: 8, marginBottom: 0 }}>
              <Input size="small" placeholder="新画板" value={newBoard} onChange={(e) => setNewBoard(e.target.value)} style={{ width: 150 }} />
              <Button
                size="icon"
                aria-label="新建画板"
                disabled={!newBoard.trim()}
                onClick={async () => {
                  await libraryApi.createBoard(newBoard.trim());
                  setNewBoard('');
                  loadSide();
                }}
              >
                <Plus size={14} />
              </Button>
            </div>
          </Card>
          <Card title="授权">
            <ul className="cw-report-list">
              {Object.entries(LICENSE_LABEL).map(([k, label]) => (
                <li key={k}>
                  <button type="button" className="cw-link-btn" onClick={() => setLicense(license === k ? undefined : k)}>
                    {label}
                  </button>
                  <span className="cw-grow" />
                  <span className="cw-muted cw-num">{facets?.licenses[k] ?? 0}</span>
                </li>
              ))}
            </ul>
            <p className="cw-muted" style={{ fontSize: 12, margin: '8px 0 0' }}>
              「仅参考」「未知」的素材放进成片时会提醒，不阻止。
            </p>
          </Card>
          <Card title="收进来的其他方式">
            <ul className="cw-report-list" style={{ fontSize: 12 }}>
              <li>任意页面粘贴截图或链接</li>
              <li>拖入文件或文件夹</li>
              <li>
                <Link href="/settings/library">素材收件箱与浏览器扩展</Link>
              </li>
            </ul>
          </Card>
        </aside>
      </div>

      <LibraryDrawer id={openId} boards={boards} onClose={() => setOpenId(null)} onChanged={refresh} onOpen={setOpenId} />
    </CwPage>
  );
}

export default function Page() {
  return (
    <Suspense fallback={null}>
      <LibraryPage />
    </Suspense>
  );
}
