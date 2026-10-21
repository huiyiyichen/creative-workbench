'use client';

/** 爆款拆解：条目详情、灵感库条目、搜索框贴链接都能打开；拆完可「照这个结构写」直接开项目。 */

import { Drawer } from 'antd';
import { Copy, ScanSearch } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';
import { Button } from '@/design/components';
import { toast } from '@/design/feedback';
import { ScanSkeleton } from '@/design/instrument';
import { libraryApi, type Breakdown, type BreakdownTarget } from '@/lib/api/_library';
import { projectsApi } from '@/lib/api/_projects';
import { breakdownIntent, wordTier } from '@/lib/breakdown';

async function copy(text: string, what: string) {
  try {
    await navigator.clipboard.writeText(text);
    toast.success(`已复制${what}`);
  } catch {
    toast.error('浏览器不允许访问剪贴板');
  }
}

export function BreakdownView({ target }: { target: BreakdownTarget }) {
  const router = useRouter();
  const [data, setData] = useState<Breakdown | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const key = JSON.stringify(target);
  const load = useCallback(
    async (force = false) => {
      setError(null);
      if (force) setData(null);
      try {
        setData(await libraryApi.breakdown(JSON.parse(key) as BreakdownTarget, force));
      } catch (err) {
        setError(err instanceof Error ? err.message : '拆解失败');
      }
    },
    [key],
  );
  useEffect(() => {
    setData(null);
    void load();
  }, [load]);
  if (error) {
    return (
      <div className="cw-bd">
        <p className="cw-error">{error}</p>
        <Button onClick={() => void load(true)}>再试一次</Button>
      </div>
    );
  }
  if (!data) return <ScanSkeleton height={320} label="在拆：读正文、抓热门评论、找钩子（约 20 秒）" />;
  const max = Math.max(0, ...data.comment_words.map((w) => w.count));
  const write = async () => {
    setBusy(true);
    try {
      const p = await projectsApi.create({ sources: [`library:${data.item_id}`], intent: breakdownIntent(data) });
      router.push(`/projects/${p.id}`);
    } catch (err) {
      toast.error(err, '没建成项目');
      setBusy(false);
    }
  };
  return (
    <div className="cw-bd">
      <header className="cw-bd-head">
        <small className="cw-muted">
          {data.platform || '网页'} · 用了 {data.comments_used} 条热门评论 · 已收进灵感库
        </small>
        <h3>{data.title}</h3>
        {data.verdict ? <p className="cw-bd-verdict">{data.verdict}</p> : null}
      </header>

      {data.hook.text ? (
        <section className="cw-bd-hook">
          <span className="cw-bd-tag">钩子{data.hook.type ? ` · ${data.hook.type}` : ''}</span>
          <blockquote>{data.hook.text}</blockquote>
          {data.hook.why ? <p className="cw-muted">{data.hook.why}</p> : null}
        </section>
      ) : null}

      {data.beats.length ? (
        <section>
          <h4 className="cw-bd-h">结构节拍</h4>
          <ol className="cw-bd-beats">
            {data.beats.map((b, i) => (
              <li key={i}>
                <span className="cw-num">{String(i + 1).padStart(2, '0')}</span>
                <b>{b.name}</b>
                <small>{b.does}</small>
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      {data.emotions.length ? (
        <section>
          <h4 className="cw-bd-h">情绪点</h4>
          <ul className="cw-bd-emo">
            {data.emotions.map((e, i) => (
              <li key={i}>
                <b>{e.point}</b>
                {e.evidence ? <small className="cw-muted">{e.evidence}</small> : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section>
        <h4 className="cw-bd-h">评论区热词</h4>
        {data.comment_words.length ? (
          <div className="cw-bd-words">
            {data.comment_words.map((w) => (
              <span key={w.word} data-tier={wordTier(w.count, max)} title={w.meaning}>
                {w.word}
                {w.count ? <sup className="cw-num">{w.count}</sup> : null}
                <small>{w.meaning}</small>
              </span>
            ))}
          </div>
        ) : (
          <p className="cw-muted">没抓到评论，这次只拆了正文。</p>
        )}
      </section>

      {data.template ? (
        <section>
          <h4 className="cw-bd-h">
            可复用结构
            <button type="button" className="cw-link-btn" onClick={() => void copy(data.template, '结构')}>
              <Copy size={12} /> 复制
            </button>
          </h4>
          <pre className="cw-bd-template">{data.template}</pre>
        </section>
      ) : null}

      {data.titles.length ? (
        <section>
          <h4 className="cw-bd-h">同款标题</h4>
          <ul className="cw-bd-titles">
            {data.titles.map((t) => (
              <li key={t}>
                <button type="button" className="cw-link-btn" onClick={() => void copy(t, '标题')}>
                  {t}
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <footer className="cw-row">
        <Button variant="primary" onClick={write} disabled={busy}>
          {busy ? '建项目中…' : '照这个结构写'}
        </Button>
        <Button onClick={() => void load(true)}>重新拆</Button>
        {data.url ? (
          <a className="cw-btn" data-variant="ghost" href={data.url} target="_blank" rel="noreferrer">
            原文 ↗
          </a>
        ) : null}
      </footer>
    </div>
  );
}

export function BreakdownDrawer({ target, onClose }: { target: BreakdownTarget | null; onClose: () => void }) {
  return (
    <Drawer open={Boolean(target)} onClose={onClose} size={560} title="爆款拆解" className="cw-drawer" destroyOnHidden>
      {target ? <BreakdownView target={target} /> : null}
    </Drawer>
  );
}

export function BreakdownButton({ target, label = '拆解爆款' }: { target: BreakdownTarget; label?: string }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button variant="ghost" icon={<ScanSearch size={15} />} onClick={() => setOpen(true)} title="为什么火：钩子、结构、情绪点、评论热词">
        {label}
      </Button>
      <BreakdownDrawer target={open ? target : null} onClose={() => setOpen(false)} />
    </>
  );
}
