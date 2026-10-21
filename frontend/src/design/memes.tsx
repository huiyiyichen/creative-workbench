'use client';

/** 今日梗雷达：今日页侧栏一张卡；写稿时底栏「今日梗」一键插入示范用法。 */

import { Popover } from 'antd';
import { Copy, RefreshCw, Sparkles } from 'lucide-react';
import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { Button, Card } from '@/design/components';
import { toast } from '@/design/feedback';
import { EmptyInstrument, ScanSkeleton } from '@/design/instrument';
import { trendingApi, type Meme, type MemeRadar } from '@/lib/api/_trending';
import { heatLabel, memeProjectHref } from '@/lib/memes';

// 同一页面里卡片和插入器共用一次请求
let shared: Promise<MemeRadar> | null = null;

function useMemes() {
  const [data, setData] = useState<MemeRadar | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(async (refresh = false) => {
    setError(null);
    if (refresh) {
      setBusy(true);
      shared = null;
    }
    try {
      shared = refresh || !shared ? trendingApi.memes(refresh) : shared;
      setData(await shared);
    } catch (err) {
      shared = null;
      setError(err instanceof Error ? err.message : '梗雷达没加载出来');
    } finally {
      setBusy(false);
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);
  return { data, error, busy, load };
}

function Heat({ h }: { h: number }) {
  return (
    <span className="cw-meme-heat" data-h={h} title={heatLabel(h)} aria-label={heatLabel(h)}>
      <i />
      <i />
      <i />
    </span>
  );
}

async function copy(text: string) {
  try {
    await navigator.clipboard.writeText(text);
    toast.success('已复制');
  } catch {
    toast.error('浏览器不允许访问剪贴板');
  }
}

function MemeRow({ m, open, onToggle }: { m: Meme; open: boolean; onToggle: () => void }) {
  return (
    <li className="cw-meme" data-open={open || undefined}>
      <button type="button" className="cw-meme-head" onClick={onToggle} aria-expanded={open}>
        <b>{m.word}</b>
        <Heat h={m.heat} />
        <small>{m.meaning}</small>
      </button>
      {open ? (
        <div className="cw-meme-body">
          {m.usage ? (
            <p className="cw-meme-usage">
              「{m.usage}」
              <button type="button" className="cw-link-btn" onClick={() => void copy(m.usage)} title="复制示范用法">
                <Copy size={12} />
              </button>
            </p>
          ) : null}
          {m.origin ? <p className="cw-muted">来源：{m.origin}</p> : null}
          {m.fit || m.platforms.length ? (
            <p className="cw-muted">
              {m.fit}
              {m.platforms.length ? ` · ${m.platforms.join(' / ')}` : ''}
            </p>
          ) : null}
          <Link className="cw-btn" data-size="small" href={memeProjectHref(m)}>
            <Sparkles size={13} /> 拿它开稿
          </Link>
        </div>
      ) : null}
    </li>
  );
}

export function MemeRadarCard() {
  const { data, error, busy, load } = useMemes();
  const [open, setOpen] = useState<string | null>(null);
  useEffect(() => {
    if (data?.items[0] && open === null) setOpen(data.items[0].word);
  }, [data, open]);
  return (
    <Card
      title="今日梗雷达"
      extra={
        <button type="button" className="cw-link-btn cw-muted" onClick={() => void load(true)} disabled={busy} title="重新扫一遍热榜和评论">
          <RefreshCw size={12} className={busy ? 'cw-spin' : undefined} /> {data?.date ? data.date.slice(5).replace('-', '/') : ''}
        </button>
      }
    >
      {error ? (
        <EmptyInstrument compact kind="dark" title="梗雷达没算出来" reason={error} actions={<Button onClick={() => void load(true)}>再试一次</Button>} />
      ) : !data || busy ? (
        <ScanSkeleton height={140} label="扫热榜标题和热门评论" />
      ) : !data.items.length ? (
        <EmptyInstrument compact kind="dark" title="今天还没扫到梗" reason={data.reason || '热榜和评论太少，晚点再看。'} />
      ) : (
        <>
          <ul className="cw-memes">
            {data.items.map((m) => (
              <MemeRow key={m.word} m={m} open={open === m.word} onToggle={() => setOpen(open === m.word ? '' : m.word)} />
            ))}
          </ul>
          {data.basis ? (
            <small className="cw-muted cw-num">
              依据 {data.basis.titles} 条热榜 · {data.basis.comments} 条评论{data.stale ? ' · 今天的还没算出来，先看上一次' : ''}
            </small>
          ) : null}
        </>
      )}
    </Card>
  );
}

/** 写稿底栏：今日梗，点一下把示范用法插到光标处。 */
export function MemeInsert({ onInsert, disabled }: { onInsert: (text: string) => void; disabled?: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <Popover
      open={open}
      onOpenChange={setOpen}
      trigger="click"
      placement="topRight"
      content={open ? <MemeInsertList onPick={(t) => { onInsert(t); setOpen(false); }} /> : null}
    >
      <Button disabled={disabled} icon={<Sparkles size={14} />} title="今天正流行的梗，点一下插入示范用法">
        今日梗
      </Button>
    </Popover>
  );
}

function MemeInsertList({ onPick }: { onPick: (text: string) => void }) {
  const { data, error } = useMemes();
  if (error) return <p className="cw-error">{error}</p>;
  if (!data) return <ScanSkeleton height={90} label="加载今日梗" />;
  if (!data.items.length) return <p className="cw-muted">{data.reason || '今天还没扫到梗'}</p>;
  return (
    <ul className="cw-meme-pick">
      {data.items.map((m) => (
        <li key={m.word}>
          <button type="button" onClick={() => onPick(m.usage || m.word)} title={m.meaning}>
            <b>{m.word}</b>
            <small>{m.usage || m.meaning}</small>
          </button>
        </li>
      ))}
    </ul>
  );
}
