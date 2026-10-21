'use client';

/** 平台原生预览：小红书笔记、抖音竖屏、B站视频页。产出物工作区与「三平台对照」共用。
 * 只模仿各平台的版式与节奏，不用平台品牌色；配色仍走 --cw-* 变量。 */

import { Bookmark, Coins, Heart, MessageCircle, Music2, Share2, Star, ThumbsUp } from 'lucide-react';
import { useEffect, useMemo, useState, type CSSProperties } from 'react';
import { estimateSeconds, fmtDuration, parseScript } from '@/lib/script';

export type PreviewContent = {
  title?: string;
  body?: string;
  tags?: string[];
  cover_text?: string;
  summary?: string;
  hook?: string;
};

type Props = { c: PreviewContent; cover?: string | null; author?: string };

function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    setReduced(mq.matches);
    const on = () => setReduced(mq.matches);
    mq.addEventListener('change', on);
    return () => mq.removeEventListener('change', on);
  }, []);
  return reduced;
}

// ── 小红书 ──

export function XhsNotePreview({ c, cover, author = '我' }: Props) {
  const tags = c.tags || [];
  return (
    <div className="cw-pv cw-pv-xhs" aria-label="小红书笔记预览">
      <div className="cw-pv-xhs-cover">
        {cover ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={cover} alt="" />
        ) : (
          <b>{c.cover_text || '封面大字'}</b>
        )}
        <span className="cw-pv-dots" aria-hidden>
          <i data-on /> <i /> <i />
        </span>
      </div>
      <div className="cw-pv-pad">
        <div className="cw-pv-author">
          <span className="cw-pv-avatar">{author.slice(0, 1)}</span>
          {author}
          <span className="cw-grow" />
          <span className="cw-pv-follow">关注</span>
        </div>
        <h4>{c.title || '标题'}</h4>
        <p className="cw-pv-body">{c.body}</p>
        {tags.length ? <p className="cw-pv-tags">{tags.map((t) => `#${t} `)}</p> : null}
        <small className="cw-pv-faint">编辑于 刚刚</small>
      </div>
      <div className="cw-pv-bar">
        <span className="cw-pv-input">说点什么…</span>
        <Heart size={16} /> <Star size={16} /> <MessageCircle size={16} />
      </div>
    </div>
  );
}

// ── 抖音 ──

export function DouyinPreview({ c, author = '我' }: Props) {
  const lines = useMemo(() => parseScript(c.body).filter((l) => l.text), [c.body]);
  const frames = useMemo(() => [{ text: c.hook || lines[0]?.text || '前三秒钩子', shot: '开场', hook: true }, ...lines.map((l) => ({ ...l, hook: false }))], [c.hook, lines]);
  const [i, setI] = useState(0);
  const reduced = useReducedMotion();
  const [playing, setPlaying] = useState(true);
  useEffect(() => setI(0), [c.body, c.hook]);
  useEffect(() => {
    if (reduced || !playing || frames.length < 2) return;
    const cur = frames[Math.min(i, frames.length - 1)];
    const ms = Math.max(1600, Math.min(4200, cur.text.length * 220));
    const t = window.setTimeout(() => setI((n) => (n + 1) % frames.length), ms);
    return () => window.clearTimeout(t);
  }, [i, frames, reduced, playing]);
  const cur = frames[Math.min(i, frames.length - 1)];
  const secs = estimateSeconds(lines) + (c.hook ? 3 : 0);
  return (
    <div className="cw-pv cw-pv-dy" aria-label="抖音竖屏预览">
      <div className="cw-pv-dy-top">
        <span>关注</span>
        <b>推荐</b>
      </div>
      <button type="button" className="cw-pv-dy-stage" onClick={() => setPlaying((p) => !p)} title={playing ? '暂停' : '播放'}>
        {cur.shot ? <span className="cw-pv-dy-shot">{cur.hook ? '前 3 秒' : `画面 · ${cur.shot}`}</span> : null}
        {cur.hook ? <b className="cw-pv-dy-hook">{cur.text}</b> : <span className="cw-pv-dy-cap">{cur.text}</span>}
        {i === 0 && c.cover_text ? <span className="cw-pv-dy-cover">{c.cover_text}</span> : null}
      </button>
      <div className="cw-pv-dy-rail" aria-hidden>
        <span className="cw-pv-avatar">{author.slice(0, 1)}</span>
        <Heart size={22} />
        <MessageCircle size={22} />
        <Bookmark size={22} />
        <Share2 size={22} />
      </div>
      <div className="cw-pv-dy-info">
        <b>@{author}</b>
        <p>
          {c.title}
          {(c.tags || []).map((t) => (
            <span key={t} className="cw-pv-dy-tag">
              {' '}#{t}
            </span>
          ))}
        </p>
        <small>
          <Music2 size={12} /> 原声 · {fmtDuration(secs)}
        </small>
      </div>
      <div className="cw-pv-dy-progress" aria-label={`第 ${i + 1} / ${frames.length} 镜`}>
        {frames.map((_, k) => (
          <i key={k} data-on={k <= i || undefined} onClick={() => setI(k)} />
        ))}
      </div>
    </div>
  );
}

// ── B站 ──

export function BiliPreview({ c, cover, author = '我' }: Props) {
  const lines = useMemo(() => parseScript(c.body), [c.body]);
  const danmaku = lines.filter((l) => l.danmaku).map((l) => l.danmaku as string);
  const speech = lines.filter((l) => l.text);
  const reduced = useReducedMotion();
  const [open, setOpen] = useState(false);
  const secs = estimateSeconds(speech);
  const flying = danmaku.length ? danmaku : ['弹幕点会显示在这里'];
  return (
    <div className="cw-pv cw-pv-bili" aria-label="B站视频页预览">
      <div className="cw-pv-bili-player">
        {cover ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={cover} alt="" />
        ) : (
          <b className="cw-pv-bili-cover">{c.cover_text || '封面大字'}</b>
        )}
        <div className="cw-pv-bili-dm" data-static={reduced || undefined} aria-label="弹幕">
          {flying.slice(0, 6).map((d, k) => (
            <span key={k} style={{ '--row': k % 4, '--delay': `${k * 1.3}s` } as CSSProperties}>
              {d}
            </span>
          ))}
        </div>
        <small className="cw-pv-bili-time">{fmtDuration(secs)}</small>
      </div>
      <div className="cw-pv-pad">
        <h4>{c.title || '标题'}</h4>
        <small className="cw-pv-faint">
          UP {author} · 弹幕点 {danmaku.length} · 约 {fmtDuration(secs)}
        </small>
        <div className="cw-pv-bili-acts" aria-hidden>
          <span>
            <ThumbsUp size={16} /> 点赞
          </span>
          <span>
            <Coins size={16} /> 投币
          </span>
          <span>
            <Star size={16} /> 收藏
          </span>
          <span>
            <Share2 size={16} /> 分享
          </span>
        </div>
        {c.hook ? <p className="cw-pv-bili-hook">开头 15 秒：{c.hook}</p> : null}
        <p className="cw-pv-body" data-clamp={!open || undefined}>
          {c.summary || '视频简介'}
        </p>
        {(c.tags || []).length ? (
          <div className="cw-pv-chips">
            {(c.tags || []).map((t) => (
              <span key={t}>{t}</span>
            ))}
          </div>
        ) : null}
        <button type="button" className="cw-link-btn" onClick={() => setOpen((o) => !o)}>
          {open ? '收起口播稿' : `展开口播稿（${speech.length} 段）`}
        </button>
        {open ? (
          <ol className="cw-pv-bili-script">
            {lines.map((l, k) =>
              l.danmaku ? (
                <li key={k} data-dm>
                  弹幕 · {l.danmaku}
                </li>
              ) : (
                <li key={k}>{l.text}</li>
              ),
            )}
          </ol>
        ) : null}
      </div>
    </div>
  );
}

export function PlatformPreview({ kind, ...props }: Props & { kind: string }) {
  if (kind === 'douyin') return <DouyinPreview {...props} />;
  if (kind === 'bilibili') return <BiliPreview {...props} />;
  return <XhsNotePreview {...props} />;
}
