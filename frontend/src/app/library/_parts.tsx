'use client';

/**
 * 灵感库的部件：条目卡片（瀑布流 / 列表）、详情抽屉、收进来（粘贴链接 / 拖入 / 剪贴板）。
 */

import { LibraryGraph, nodeHref } from '@/design/graph';
import { parseUTC } from '@/lib/datetime';
import Link from 'next/link';
import { Drawer, Input, Popover, Select, Spin, message } from 'antd';
import { ExternalLink, FileAudio, FileType2, Link2, Palette, Sparkles, Trash2, Wand2 } from 'lucide-react';
import { useCallback, useEffect, useState, type CSSProperties, type ReactNode } from 'react';
import { Button, Chip } from '@/design/components';
import { color, mediaColor } from '@/design/tokens';
import {
  ASSET_LABEL,
  KIND_LABEL,
  LICENSE_LABEL,
  libraryApi,
  libraryFileUrl,
  type Board,
  type LibraryItem,
  type LibraryItemDetail,
  type License,
  obsidianOpenUrl,
  type GraphData,
  type ObsidianSettings,
} from '@/lib/api/_library';
import { formatDuration, waveform } from '@/lib/collection';
import { SignalArt } from '@/design/signal-art';

export const KIND_COLOR: Record<string, string> = {
  article: mediaColor.article,
  video: mediaColor.video,
  image: mediaColor.image,
  post: mediaColor.article,
  prompt: mediaColor.prompt,
  repo: mediaColor.repo,
  asset: color.wh,
  generated: color.mg,
  link: color.dim,
};

export const LICENSE_TONE: Record<License, string> = {
  own: color.gr,
  commercial: color.cy,
  reference: color.yl,
  unknown: color.faint,
  ai: color.mg,
};

export const RELATION_LABEL: Record<string, string> = {
  same_event: '同一事件',
  same_tag: '同标签',
  same_author: '同作者',
  similar: '语义相似',
  used_in_project: '用于项目',
  distilled: '提炼',
  generated: '生成',
  extracted: '提取',
  wikilink: '双链',
  manual: '手动',
};

function errText(err: unknown): string {
  return err instanceof Error ? err.message : '请求失败';
}

export function itemImage(item: Pick<LibraryItem, 'id' | 'thumb' | 'cover_url'>, size: 'small' | 'large' = 'small'): string | null {
  if (item.thumb) return libraryFileUrl(item.id, size);
  return item.cover_url || null;
}

function Wave({ values }: { values: number[] }) {
  return (
    <svg viewBox={`0 0 ${values.length * 4} 40`} preserveAspectRatio="none" className="cw-lib-wave" aria-hidden>
      {values.map((v, i) => (
        <rect key={i} x={i * 4} y={20 - v * 18} width={2.4} height={Math.max(1, v * 36)} rx={1} />
      ))}
    </svg>
  );
}

/** 没有图片的条目：提示词显示正文，配色显示色块，音频显示波形，其他用生成封面 */
function Placeholder({ item }: { item: LibraryItem }) {
  if (item.asset_kind === 'audio') {
    const wave = (item.meta?.waveform as number[] | undefined) || waveform(item.title, 40);
    return (
      <div className="cw-lib-ph" data-kind="audio">
        <FileAudio size={18} />
        <Wave values={wave} />
      </div>
    );
  }
  if (item.palette && item.palette.length && item.asset_kind === 'palette') {
    return (
      <div className="cw-lib-ph cw-lib-swatches">
        {item.palette.map((c) => (
          <i key={c} style={{ background: c }} />
        ))}
      </div>
    );
  }
  if (item.kind === 'prompt') {
    return (
      <div className="cw-lib-ph" data-kind="prompt">
        <p>
          <span aria-hidden>›</span> {(item.body || item.title).slice(0, 160)}
          <i aria-hidden />
        </p>
      </div>
    );
  }
  if (item.kind === 'link' || item.kind === 'article' || item.kind === 'post') {
    return (
      <div className="cw-lib-ph cw-work-art" data-kind="gen" style={{ aspectRatio: '16 / 9', height: 'auto' }}>
        <SignalArt title={item.title} kind={item.kind} />
      </div>
    );
  }
  if (item.asset_kind === 'font') {
    return (
      <div className="cw-lib-ph" data-kind="text">
        <FileType2 size={18} />
        <p>{String(item.meta?.family || item.title)}</p>
      </div>
    );
  }
  return (
    <div className="cw-lib-ph" data-kind="gen" style={{ aspectRatio: '16 / 9' }}>
      <SignalArt title={item.title} kind={item.kind} />
    </div>
  );
}

export function LibraryCard({
  item,
  selected,
  selecting,
  onOpen,
  onToggle,
}: {
  item: LibraryItem;
  selected?: boolean;
  selecting?: boolean;
  onOpen: (id: number) => void;
  onToggle?: (id: number) => void;
}) {
  const img = itemImage(item);
  const ratio = item.width && item.height ? item.height / item.width : item.kind === 'video' ? 9 / 16 : null;
  const c = KIND_COLOR[item.kind] || color.dim;
  return (
    <figure className="cw-lib-card" data-selected={selected ? 'true' : undefined} style={{ '--c': c } as CSSProperties}>
      <button
        type="button"
        className="cw-lib-media"
        onClick={() => (selecting && onToggle ? onToggle(item.id) : onOpen(item.id))}
        style={{ background: item.dominant_color || undefined, aspectRatio: img && ratio ? `${1 / Math.min(2.2, Math.max(0.45, ratio))}` : undefined }}
        aria-label={item.title}
      >
        {img ? (
          // 本地缩略图或平台封面
          // eslint-disable-next-line @next/next/no-img-element
          <img src={img} alt="" loading="lazy" />
        ) : (
          <Placeholder item={item} />
        )}
        {item.duration ? <span className="cw-cover-badge cw-num">{formatDuration(item.duration)}</span> : null}
        {selecting ? <span className="cw-lib-check" aria-hidden>{selected ? '✓' : ''}</span> : null}
      </button>
      <figcaption>
        <span className="cw-lib-kind">{item.asset_kind ? ASSET_LABEL[item.asset_kind] : KIND_LABEL[item.kind]}</span>
        <span className="cw-lib-title" title={item.title}>
          {item.title}
        </span>
        {item.license !== 'unknown' ? (
          <span className="cw-lib-lic" style={{ '--c': LICENSE_TONE[item.license] } as CSSProperties}>
            {LICENSE_LABEL[item.license]}
          </span>
        ) : null}
      </figcaption>
    </figure>
  );
}

function linkPlatform(url: string): string {
  try {
    const h = new URL(url).hostname.replace(/^www\.|^m\./, '');
    if (h.endsWith('bilibili.com') || h === 'b23.tv') return 'B站';
    if (h.endsWith('douyin.com')) return '抖音';
    if (h.endsWith('xiaohongshu.com') || h === 'xhslink.com') return '小红书';
    if (h.endsWith('youtube.com') || h === 'youtu.be') return 'YouTube';
    if (h === 'github.com') return 'GitHub';
    if (h === 'x.com' || h === 'twitter.com') return 'X';
    if (h.endsWith('zhihu.com')) return '知乎';
    return h;
  } catch {
    return '链接';
  }
}

export function AddBar({ onAdded }: { onAdded: (items: LibraryItem[]) => void }) {
  const [link, setLink] = useState('');
  const [busy, setBusy] = useState(false);

  const addLink = async () => {
    const v = link.trim();
    if (!v) return;
    setBusy(true);
    try {
      const it = /^https?:\/\//.test(v) ? await libraryApi.fromLink(v) : await libraryApi.text(v, 'prompt');
      setLink('');
      onAdded([it]);
      message.success(`已收进：${it.title.slice(0, 30)}`);
    } catch (err) {
      message.error(errText(err));
    } finally {
      setBusy(false);
    }
  };

  const upload = async (files: File[]) => {
    if (!files.length) return;
    setBusy(true);
    try {
      const r = await libraryApi.upload(files);
      onAdded(r.items);
      message.success(`导入 ${r.items.length} 个${r.errors.length ? `，${r.errors.length} 个失败` : ''}`);
    } catch (err) {
      message.error(errText(err));
    } finally {
      setBusy(false);
    }
  };

  const plat = /^https?:\/\//.test(link.trim()) ? linkPlatform(link.trim()) : link.trim() ? '提示词 / 文本' : null;
  return (
    <div className="cw-lib-add" data-ready={plat ? 'true' : undefined}>
      {plat ? <span className="cw-lib-add-plat">{plat}</span> : null}
      <Input
        size="large"
        value={link}
        onChange={(e) => setLink(e.target.value)}
        onPressEnter={addLink}
        placeholder="粘贴链接（B站、YouTube、GitHub、小红书、任意网页）或一段提示词，回车收进来"
        prefix={<Link2 size={15} />}
        disabled={busy}
      />
      <Button variant="primary" onClick={addLink} disabled={busy || !link.trim()}>
        {busy ? '收进中…' : '收进来'}
      </Button>
      <label className="cw-btn">
        上传文件
        <input type="file" multiple hidden onChange={(e) => upload(Array.from(e.target.files || []))} />
      </label>
    </div>
  );
}

export function useDropAndPaste(onFiles: (files: File[], method: 'file' | 'clipboard') => void, onText: (text: string) => void) {
  const [dragging, setDragging] = useState(false);
  useEffect(() => {
    const onPaste = (e: ClipboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable)) return;
      const files = Array.from(e.clipboardData?.files || []);
      if (files.length) {
        e.preventDefault();
        onFiles(files, 'clipboard');
        return;
      }
      const text = e.clipboardData?.getData('text')?.trim();
      if (text) {
        e.preventDefault();
        onText(text);
      }
    };
    const onDragOver = (e: DragEvent) => {
      if (e.dataTransfer?.types.includes('Files')) {
        e.preventDefault();
        setDragging(true);
      }
    };
    const onDragLeave = (e: DragEvent) => {
      if (!e.relatedTarget) setDragging(false);
    };
    const onDrop = (e: DragEvent) => {
      const files = Array.from(e.dataTransfer?.files || []);
      setDragging(false);
      if (files.length) {
        e.preventDefault();
        onFiles(files, 'file');
      }
    };
    window.addEventListener('paste', onPaste);
    window.addEventListener('dragover', onDragOver);
    window.addEventListener('dragleave', onDragLeave);
    window.addEventListener('drop', onDrop);
    return () => {
      window.removeEventListener('paste', onPaste);
      window.removeEventListener('dragover', onDragOver);
      window.removeEventListener('dragleave', onDragLeave);
      window.removeEventListener('drop', onDrop);
    };
  }, [onFiles, onText]);
  return dragging;
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="cw-basis-row">
      <span className="cw-muted">{label}</span>
      <div>{children}</div>
    </div>
  );
}

/** 详情里的局部图谱（一度、二度）；点收藏节点切换详情，其他节点跳到对应页面 */
function LocalGraph({ id, onOpen }: { id: number; onOpen: (id: number) => void }) {
  const [data, setData] = useState<GraphData | null>(null);
  useEffect(() => {
    let alive = true;
    libraryApi
      .graph({ center: `item:${id}`, depth: 2 })
      .then((g) => alive && setData(g))
      .catch(() => alive && setData(null));
    return () => {
      alive = false;
    };
  }, [id]);
  if (!data || data.nodes.length < 2) return null;
  return (
    <>
      <h3 className="cw-detail-h">局部图谱</h3>
      <LibraryGraph
        data={data}
        height={260}
        onSelect={(n) => {
          if (!n || n.key === `item:${id}`) return;
          if (n.type === 'item') onOpen(Number(n.key.split(':')[1]));
          else window.location.assign(nodeHref(n));
        }}
      />
    </>
  );
}

let obsidianCache: Promise<ObsidianSettings | null> | null = null;

/** Obsidian 设置（用于「在 Obsidian 打开」）；整个会话只取一次 */
export function useObsidian(): ObsidianSettings | null {
  const [s, setS] = useState<ObsidianSettings | null>(null);
  useEffect(() => {
    obsidianCache ??= libraryApi.obsidian().catch(() => null);
    let alive = true;
    void obsidianCache.then((v) => alive && setS(v));
    return () => {
      alive = false;
    };
  }, []);
  return s;
}

export function LibraryDrawer({
  id,
  boards,
  onClose,
  onChanged,
  onOpen,
}: {
  id: number | null;
  boards: Board[];
  onClose: () => void;
  onChanged: () => void;
  onOpen: (id: number) => void;
}) {
  const [data, setData] = useState<LibraryItemDetail | null>(null);
  const [tags, setTags] = useState<string[]>([]);
  const [notes, setNotes] = useState('');
  const [frameAt, setFrameAt] = useState('1');
  const obsidian = useObsidian();

  const load = useCallback(async () => {
    if (id === null) return;
    try {
      const d = await libraryApi.item(id);
      setData(d);
      setTags(d.tags);
      setNotes(d.my_notes || '');
    } catch (err) {
      message.error(errText(err));
    }
  }, [id]);

  useEffect(() => {
    setData(null);
    void load();
  }, [load]);

  const save = async (body: Parameters<typeof libraryApi.update>[1], ok = '已保存') => {
    if (!data) return;
    try {
      await libraryApi.update(data.id, body);
      message.success(ok);
      await load();
      onChanged();
    } catch (err) {
      message.error(errText(err));
    }
  };

  const img = data ? itemImage(data, 'large') : null;
  const meta = data?.meta || {};
  return (
    <Drawer open={id !== null} onClose={onClose} size={560} closable={false} destroyOnHidden className="cw-drawer" styles={{ body: { padding: 0 } }}>
      {!data ? (
        <div className="cw-detail cw-detail-loading">
          <Spin />
        </div>
      ) : (
        <article className="cw-detail">
          <div className="cw-detail-actions">
            {obsidian?.vault_name && data.obsidian_path ? (
              <a className="cw-btn" data-variant="ghost" href={obsidianOpenUrl(obsidian, data.obsidian_path)}>
                在 Obsidian 打开
              </a>
            ) : null}
            {data.url ? (
              <a className="cw-btn" data-variant="ghost" href={data.url} target="_blank" rel="noreferrer">
                <ExternalLink size={15} />
                原链接
              </a>
            ) : null}
            {data.has_file ? (
              <a className="cw-btn" data-variant="ghost" href={libraryFileUrl(data.id, 'original')} target="_blank" rel="noreferrer">
                原文件
              </a>
            ) : null}
            {data.content_id ? (
              <Link className="cw-btn" data-variant="ghost" href={`/items/${data.content_id}`}>
                条目详情
              </Link>
            ) : null}
            <Button variant="ghost" onClick={onClose}>
              关闭
            </Button>
          </div>
          {img ? (
            <div className="cw-lib-preview" style={{ background: data.dominant_color || undefined }}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={img} alt="" />
            </div>
          ) : null}
          {data.asset_kind === 'audio' && data.has_file ? <audio controls src={libraryFileUrl(data.id, 'original')} style={{ width: '100%' }} /> : null}
          {data.asset_kind === 'motion' && data.has_file && data.mime?.startsWith('video/') ? (
            <div className="cw-lib-frame">
              <video controls src={libraryFileUrl(data.id, 'original')} style={{ width: '100%', borderRadius: 8 }} />
              <div className="cw-filters">
                <span className="cw-muted">截帧时间（秒）</span>
                <Input value={frameAt} onChange={(e) => setFrameAt(e.target.value)} style={{ width: 80 }} />
                <Button
                  onClick={async () => {
                    try {
                      const it = await libraryApi.frame({ item_id: data.id, at: Number(frameAt) || 0 });
                      message.success('已截帧存入灵感库');
                      onChanged();
                      onOpen(it.id);
                    } catch (err) {
                      message.error(errText(err));
                    }
                  }}
                >
                  截帧
                </Button>
              </div>
            </div>
          ) : null}
          <Input.TextArea
            className="cw-lib-title-edit"
            defaultValue={data.title}
            autoSize
            onBlur={(e) => e.target.value.trim() && e.target.value !== data.title && save({ title: e.target.value.trim() })}
          />
          <div className="cw-item-meta" style={{ marginBottom: 10 }}>
            <span>{data.asset_kind ? ASSET_LABEL[data.asset_kind] : KIND_LABEL[data.kind]}</span>
            {data.platform ? <span>{data.platform}</span> : null}
            {data.author ? <span>{data.author}</span> : null}
            {data.width && data.height ? (
              <span className="cw-num">
                {data.width}×{data.height}
              </span>
            ) : null}
            {data.duration ? <span className="cw-num">{formatDuration(data.duration)}</span> : null}
            <span>收于 {parseUTC(data.created_at).toLocaleDateString('zh-CN')}</span>
          </div>
          <div className="cw-basis">
            <Row label="授权">
              <Select
                size="small"
                value={data.license}
                style={{ width: 130 }}
                onChange={(v) => save({ license: v as License }, '授权已更新')}
                options={Object.entries(LICENSE_LABEL).map(([value, label]) => ({ value, label }))}
              />
            </Row>
            <Row label="标签">
              <Select
                mode="tags"
                size="small"
                value={tags}
                style={{ minWidth: 260 }}
                onChange={setTags}
                onBlur={() => JSON.stringify(tags) !== JSON.stringify(data.tags) && save({ tags })}
                placeholder="回车添加"
              />
              {data.ai_tags.length ? <span className="cw-muted">AI：{data.ai_tags.join('、')}</span> : null}
            </Row>
            {data.palette?.length ? (
              <Row label="配色">
                <span className="cw-lib-swatches-inline">
                  {data.palette.map((c) => (
                    <i key={c} style={{ background: c }} title={c} />
                  ))}
                </span>
              </Row>
            ) : null}
            {meta.family ? <Row label="字体">{`${meta.family} ${meta.style || ''} ${meta.weight || ''}`}</Row> : null}
            {meta.model || meta.params ? (
              <Row label="生成">
                {meta.model ? <span>{String(meta.model)}</span> : null}
                {meta.params ? (
                  <span className="cw-muted cw-num">
                    {Object.entries(meta.params as Record<string, string>)
                      .slice(0, 5)
                      .map(([k, v]) => `${k} ${v}`)
                      .join(' · ')}
                  </span>
                ) : null}
              </Row>
            ) : null}
            <Row label="画板">
              {data.boards.map((b) => (
                <Chip key={b.id}>{b.name}</Chip>
              ))}
              <Select
                size="small"
                placeholder="加入画板"
                style={{ width: 140 }}
                value={null}
                onChange={async (bid: number) => {
                  await libraryApi.addToBoard(bid, [data.id]);
                  await load();
                  onChanged();
                }}
                options={boards.filter((b) => !data.boards.some((x) => x.id === b.id)).map((b) => ({ value: b.id, label: b.name }))}
              />
            </Row>
          </div>
          {data.body ? (
            <>
              <h3 className="cw-detail-h">{data.kind === 'prompt' || meta.prompt ? '提示词' : '正文'}</h3>
              <pre className="cw-lib-body">{data.body}</pre>
              {meta.negative_prompt ? <pre className="cw-lib-body cw-muted">反向：{String(meta.negative_prompt)}</pre> : null}
            </>
          ) : null}
          <h3 className="cw-detail-h">我的笔记</h3>
          <Input.TextArea value={notes} onChange={(e) => setNotes(e.target.value)} onBlur={() => notes !== (data.my_notes || '') && save({ my_notes: notes })} autoSize={{ minRows: 2 }} placeholder="写点什么；也会同步到 Obsidian 的「我的笔记」" />
          <LocalGraph id={data.id} onOpen={onOpen} />
          <h3 className="cw-detail-h">关联</h3>
          {data.related.length === 0 ? (
            <p className="cw-muted">还没有关联</p>
          ) : (
            <ul className="cw-others">
              {data.related.map((r) => (
                <li key={`${r.type}-${r.id}-${r.relation}`} style={{ '--c': KIND_COLOR[r.kind || ''] || color.dim } as CSSProperties}>
                  <i />
                  <span className="cw-muted">{RELATION_LABEL[r.relation] || r.relation}</span>
                  {r.type === 'item' ? (
                    <button type="button" className="cw-link-btn" onClick={() => onOpen(r.id)}>
                      {r.title}
                    </button>
                  ) : r.type === 'content' ? (
                    <Link href={`/items/${r.id}`}>{r.title}</Link>
                  ) : r.type === 'dossier' ? (
                    <Link href={`/dossiers/${r.id}`}>{r.title}</Link>
                  ) : r.type === 'note' ? (
                    <Link href={`/notes?focus=${r.id}`}>{r.title}</Link>
                  ) : (
                    <span>{r.title}</span>
                  )}
                  {r.link_id ? (
                    <button type="button" className="cw-link-btn cw-muted" onClick={async () => { await libraryApi.unlink(r.link_id!); await load(); }}>
                      移除
                    </button>
                  ) : (
                    <span />
                  )}
                </li>
              ))}
            </ul>
          )}
          <div className="cw-detail-tools" style={{ marginTop: 18 }}>
            <Link className="cw-btn" href={`/projects/new?source=library:${data.id}`}>
              <Wand2 size={15} />
              用于新项目
            </Link>
            <Popover
              trigger="click"
              content={
                <div style={{ display: 'grid', gap: 6 }}>
                  <Button icon={<Palette size={14} />} onClick={async () => { try { const r = await libraryApi.distill('style', data.title, [data.id]); message.success(`已提炼风格「${r.name}」`); } catch (err) { message.error(errText(err)); } }}>
                    提炼为风格
                  </Button>
                  <Button icon={<Sparkles size={14} />} onClick={async () => { try { const r = await libraryApi.distill('template', data.title, [data.id]); message.success(`已提炼模板「${r.name}」`); } catch (err) { message.error(errText(err)); } }}>
                    提炼为模板
                  </Button>
                </div>
              }
            >
              <Button icon={<Sparkles size={15} />}>提炼</Button>
            </Popover>
            <span className="cw-grow" />
            <Button
              variant="ghost"
              icon={<Trash2 size={15} />}
              onClick={async () => {
                await libraryApi.remove(data.id);
                message.success('已移出灵感库');
                onChanged();
                onClose();
              }}
            >
              移出
            </Button>
          </div>
        </article>
      )}
    </Drawer>
  );
}
