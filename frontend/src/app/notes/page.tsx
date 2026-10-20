'use client';

/**
 * 随笔（改造方案 6.4）：按日期排成时间线（像日记），按标签、关联对象筛选；写一句就存，
 * 支持 #标签、[[双链]]、粘贴图片、录音（千问转写）；保存后显示相关的收藏和热点。
 */

import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { Input, message } from 'antd';
import { Trash2 } from 'lucide-react';
import { Suspense, useCallback, useEffect, useState } from 'react';
import { Button, Card, CwPage, TopBar } from '@/design/components';
import { libraryApi, libraryFileUrl, type NoteRelated } from '@/lib/api/_library';
import { NoteComposer, renderNoteBody } from '@/design/notes';

function errText(err: unknown): string {
  return err instanceof Error ? err.message : '请求失败';
}

function NotesPage() {
  const params = useSearchParams();
  const focus = params.get('focus');
  const [tag, setTag] = useState<string | undefined>(params.get('tag') || undefined);
  const [q, setQ] = useState('');
  const [data, setData] = useState<Awaited<ReturnType<typeof libraryApi.notes>> | null>(null);
  const [related, setRelated] = useState<NoteRelated | null>(null);
  const [editing, setEditing] = useState<number | null>(null);
  const [draft, setDraft] = useState('');
  const [days, setDays] = useState(14);

  const load = useCallback(() => {
    libraryApi
      .notes({ tag, q: q || undefined, days })
      .then(setData)
      .catch((err) => message.error(errText(err)));
  }, [tag, q, days]);

  useEffect(() => {
    const t = setTimeout(load, 200);
    return () => clearTimeout(t);
  }, [load]);

  useEffect(() => {
    if (focus && data) document.getElementById(`note-${focus}`)?.scrollIntoView({ block: 'center' });
  }, [focus, data]);

  return (
    <CwPage>
      <TopBar title="随笔" sub="Alt+N 在任何页面随手记">
        <nav className="cw-seg" aria-label="灵感库分页">
          <Link href="/library">收藏</Link>
          <Link href="/notes" aria-current="page">
            随笔
          </Link>
          <Link href="/library/styles">风格与模板</Link>
          <Link href="/library/graph">图谱</Link>
        </nav>
      </TopBar>
      <div className="cw-today">
        <section>
          <NoteComposer
            onSaved={(n) => {
              setRelated(n.related || null);
              load();
            }}
          />
          <div className="cw-filters" style={{ marginTop: 16 }}>
            <Input.Search allowClear placeholder="搜索随笔" style={{ width: 240 }} value={q} onChange={(e) => setQ(e.target.value)} />
            {tag ? (
              <button type="button" className="cw-chip" onClick={() => setTag(undefined)}>
                #{tag} ✕
              </button>
            ) : null}
          </div>
          {!data ? (
            <div className="cw-empty">加载中…</div>
          ) : data.days.length === 0 ? (
            <div className="cw-empty">{tag || q ? '没有匹配的随笔' : '最近没有随笔'}</div>
          ) : (
            data.days.map((d) => (
              <div key={d.date} className="cw-note-day">
                <h3 className="cw-num">{d.date}</h3>
                {d.notes.map((n) => (
                  <article key={n.id} id={`note-${n.id}`} className="cw-note" data-focus={String(n.id) === focus ? 'true' : undefined}>
                    <span className="cw-note-time cw-num">{new Date(n.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false })}</span>
                    <div className="cw-note-body">
                      {editing === n.id ? (
                        <>
                          <Input.TextArea value={draft} onChange={(e) => setDraft(e.target.value)} autoSize={{ minRows: 2 }} autoFocus />
                          <div className="cw-filters" style={{ margin: '6px 0 0' }}>
                            <Button
                              variant="primary"
                              onClick={async () => {
                                await libraryApi.updateNote(n.id, draft);
                                setEditing(null);
                                load();
                              }}
                            >
                              保存
                            </Button>
                            <Button variant="ghost" onClick={() => setEditing(null)}>
                              取消
                            </Button>
                          </div>
                        </>
                      ) : (
                        <div onDoubleClick={() => { setEditing(n.id); setDraft(n.body); }}>{renderNoteBody(n.body, n.links, setTag)}</div>
                      )}
                      {n.image_item_ids.length ? (
                        <div className="cw-note-images">
                          {n.image_item_ids.map((id) => (
                            // eslint-disable-next-line @next/next/no-img-element
                            <img key={id} src={libraryFileUrl(id)} alt="" />
                          ))}
                        </div>
                      ) : null}
                      <div className="cw-item-meta">
                        {n.audio ? <span>录音{n.transcript_status === 'done' ? ' · 已转写' : n.transcript_status === 'not_configured' ? ' · 未配置转写' : ''}</span> : null}
                        {n.source !== 'app' ? <span>来自{n.source === 'tray' ? '托盘' : 'Obsidian'}</span> : null}
                        <button type="button" className="cw-link-btn" onClick={() => { setEditing(n.id); setDraft(n.body); }}>
                          编辑
                        </button>
                        <Link href={`/studio?notes=${n.id}`}>用于新项目</Link>
                        <button
                          type="button"
                          className="cw-link-btn"
                          aria-label="删除"
                          onClick={async () => {
                            await libraryApi.deleteNote(n.id);
                            load();
                          }}
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            ))
          )}
          {!tag && !q && data ? (
            <div style={{ textAlign: 'center', marginTop: 12 }}>
              <Button onClick={() => setDays(days + 30)}>更早</Button>
            </div>
          ) : null}
        </section>
        <aside className="cw-today-side">
          {related && (related.favorites.length || related.hot.length) ? (
            <Card title="刚记下的这条，相关的">
              <ul className="cw-report-list">
                {related.favorites.map((r) => (
                  <li key={`f${r.content_id}`}>
                    <span className="cw-muted">收藏</span>
                    <Link href={`/items/${r.content_id}`}>{r.title}</Link>
                  </li>
                ))}
                {related.hot.map((r) => (
                  <li key={`h${r.content_id}`}>
                    <span className="cw-muted">热点</span>
                    <Link href={`/items/${r.content_id}`}>{r.title}</Link>
                  </li>
                ))}
              </ul>
            </Card>
          ) : null}
          <Card title="标签">
            <div className="cw-chips">
              {(data?.tags || []).map(([t, n]) => (
                <button key={t} type="button" className="cw-chip" onClick={() => setTag(t)}>
                  #{t} <span className="cw-num">{n}</span>
                </button>
              ))}
              {data && !data.tags.length ? <span className="cw-muted">还没有标签</span> : null}
            </div>
          </Card>
        </aside>
      </div>
    </CwPage>
  );
}

export default function Page() {
  return (
    <Suspense fallback={null}>
      <NotesPage />
    </Suspense>
  );
}
