'use client';

/**
 * 发现区的招牌组件（12.3）：结论标记、指标示波、信息流条目、今天的信号时间线、追踪词点阵、共振矩阵、
 * 升温榜行、带缺口曲线、条目详情（抽屉与独立页共用）。
 */

import { BreakdownButton } from '@/design/breakdown';
import { FeishuButton } from './feishu';
import Link from 'next/link';
import { Drawer, Input, Popover, Spin, message } from 'antd';
import { Bookmark, ExternalLink, Maximize2, Sparkles, ThumbsDown, ThumbsUp, Unlink, Workflow } from 'lucide-react';
import { useCallback, useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import { Button, Cover, Segmented, Sparkline } from '@/design/components';
import { color } from '@/design/tokens';
import { favoritesApi } from '@/lib/api/_admin-api';
import { mediaUrl } from '@/lib/api/_collection';
import {
  discoverApi,
  type CommentList,
  type ItemCard,
  type ItemDetail,
  type MetricView,
  type ResonanceMatrix,
  type TodaySignals,
  type TopicStatus,
  type Verdict,
} from '@/lib/api/_discover';
import { METRIC_LABEL, PLATFORM_LABEL, compactNumber, formatDuration, primarySeries, relativeTime } from '@/lib/collection';
import {
  BASIS_LABEL,
  JOURNEY_LABEL,
  SIGNAL_RANGES,
  SIGNAL_TITLE,
  type SignalRange,
  MEDIA_LABEL,
  STATUS_COLOR,
  STATUS_LABEL,
  VERDICT_COLOR,
  VERDICT_LABEL,
  dayPosition,
  gappedPaths,
  heatOpacity,
  mediaKindColor,
  metricText,
  rulerTicks,
  topPlatforms,
} from '@/lib/discover';
import { clusterClips, timelineView } from '@/lib/timeline';
import { fmtHM } from '@/lib/time-cn';
import { EmptyInstrument } from './instrument';

export function platformName(p: string | null | undefined): string {
  return PLATFORM_LABEL[p || 'web'] || p || '网页';
}

function errText(err: unknown): string {
  return err instanceof Error ? err.message : '请求失败';
}

// ── 结论标记 ──

export function VerdictMark({ verdict, user, size = 'default' }: { verdict: Verdict | null; user?: boolean; size?: 'default' | 'small' }) {
  if (!verdict) return <span className="cw-verdict" data-size={size} data-empty="true">未判断</span>;
  return (
    <span
      className="cw-verdict"
      data-size={size}
      style={{ '--c': VERDICT_COLOR[verdict] } as CSSProperties}
      title={user ? '你改过的结论' : undefined}
    >
      <b />
      {VERDICT_LABEL[verdict]}
      {user ? <small>·你</small> : null}
    </span>
  );
}

export function StatusTag({ status }: { status: TopicStatus | null | undefined }) {
  if (!status) return <span className="cw-status" data-empty="true">观测不足</span>;
  return (
    <span className="cw-status" style={{ '--c': STATUS_COLOR[status] } as CSSProperties}>
      {STATUS_LABEL[status]}
    </span>
  );
}

// ── 指标示波：观测柱 + 原始值 + 变化量 + 观测时间 ──

export function MetricScope({ metric, accent }: { metric: MetricView; accent: string }) {
  const t = metricText(metric);
  if (!metric.metric)
    return (
      <div className="cw-scope" data-empty="true">
        <span className="cw-scope-none">{t.value}</span>
        <span className="cw-scope-time">按发布时间排序</span>
      </div>
    );
  const obs = Math.min(12, Math.max(2, metric.observations ?? 2));
  return (
    <div className="cw-scope" style={{ '--c': accent } as CSSProperties}>
      <div className="cw-scope-bars" aria-hidden>
        {Array.from({ length: obs }, (_, i) => (
          <i key={i} style={{ height: `${25 + (75 * (i + 1)) / obs}%` }} data-last={i === obs - 1 ? 'true' : undefined} />
        ))}
      </div>
      <div className="cw-scope-val">
        <span className="cw-muted">{t.label}</span> <b className="cw-num">{t.value}</b>
        {t.delta ? <span className="cw-num cw-up">{t.delta}</span> : null}
      </div>
      {t.observed ? <div className="cw-scope-time">{t.observed}</div> : null}
    </div>
  );
}

// ── 信息流条目 ──

export function FeedItem({
  item,
  selected,
  hovered,
  onOpen,
  onHover,
  showVerdict = true,
}: {
  item: ItemCard;
  selected?: boolean;
  hovered?: boolean;
  onOpen: (id: number) => void;
  onHover?: (id: number | null) => void;
  /** 列表里只有前 20% 的「值得做」才显示结论，其余行不标（结论少才有意义） */
  showVerdict?: boolean;
}) {
  const c = mediaKindColor(item.media_type);
  const fresh = item.key_points.includes('新出现');
  const points = item.key_points.filter((k) => k !== '新出现');
  const cover = item.cover_asset_id ? mediaUrl(item.cover_asset_id) : null;
  return (
    <li
      className="cw-item"
      data-art-host
      data-selected={selected ? 'true' : undefined}
      data-hovered={hovered ? 'true' : undefined}
      style={{ '--c': c } as CSSProperties}
      onPointerEnter={onHover ? () => onHover(item.id) : undefined}
      onPointerLeave={onHover ? () => onHover(null) : undefined}
    >
      <button type="button" className="cw-item-cover" onClick={() => onOpen(item.id)} aria-label={`打开 ${item.title}`}>
        <Cover
          src={cover}
          title={item.title}
          color={item.cover_color}
          orientation={item.media_type === 'video' ? 'landscape' : 'landscape'}
          kind={item.media_type}
          badge={formatDuration(item.duration)}
        />
        <span className="cw-item-kind">{MEDIA_LABEL[item.media_type] || '文章'}</span>
      </button>
      <div className="cw-item-main">
        <button type="button" className="cw-item-title" onClick={() => onOpen(item.id)}>
          {fresh ? <i className="cw-fresh" title="新出现" aria-label="新出现" /> : null}
          {item.title}
        </button>
        <div className="cw-item-meta">
          <span className="cw-plat">{platformName(item.platform)}</span>
          {item.author ? <span>{item.author}</span> : item.source_name ? <span>{item.source_name}</span> : null}
          <span>{relativeTime(item.published_at || item.crawled_at)}发布</span>
        </div>
        {item.verdict === 'skip' || (showVerdict && item.verdict === 'worth') ? (
          <div className="cw-item-verdict">
            <VerdictMark verdict={item.verdict} user={Boolean(item.user_verdict)} size="small" />
            {points.length ? <span className="cw-num">{points.join(' · ')}</span> : null}
          </div>
        ) : points.length ? (
          <div className="cw-item-verdict">
            <span className="cw-num cw-muted">{points.join(' · ')}</span>
          </div>
        ) : null}
      </div>
      {item.metric.metric ? (
        <MetricScope metric={item.metric} accent={c} />
      ) : item.event && item.event.members > 1 ? (
        <div className="cw-item-event" title={`同一事件在 ${item.event.members} 处出现`}>
          <span aria-hidden>
            {Array.from({ length: Math.min(8, item.event.members) }, (_, i) => (
              <i key={i} />
            ))}
          </span>
          <small>同一事件 {item.event.members} 条</small>
        </div>
      ) : (
        <span aria-hidden />
      )}
      <FeedActions item={item} />
    </li>
  );
}

/** 信息流行尾：收藏（一次点击，收进灵感库）+ 开始创作（以这条为主来源新建项目） */
function FeedActions({ item }: { item: ItemCard }) {
  const [fav, setFav] = useState(item.is_favorited);
  const [busy, setBusy] = useState(false);
  return (
    <div className="cw-item-acts">
      <button
        type="button"
        className="cw-btn"
        data-icon="true"
        aria-pressed={fav}
        aria-label={fav ? '已收藏' : '收藏'}
        title={fav ? '已收藏' : '收藏到灵感库'}
        disabled={busy || fav}
        onClick={async () => {
          setBusy(true);
          try {
            await favoritesApi.create({ target_type: 'content', target_id: item.id, title: item.title, url: item.url, source_name: item.source_name });
            setFav(true);
          } catch {
            /* 失败保持未收藏，用户可再点 */
          } finally {
            setBusy(false);
          }
        }}
      >
        <Bookmark size={15} fill={fav ? 'currentColor' : 'none'} aria-hidden />
      </button>
      <Link className="cw-btn cw-item-create" href={`/projects/new?source=content:${item.id}`}>
        开始创作
      </Link>
    </div>
  );
}

// ── 今天的信号 ──

function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
}

/** 从 0 缓动到 target（1.6 s，easeOutCubic）；key 变化时重扫；减少动态时直接到位。 */
function useSweep(target: number, key: string): number {
  const [v, setV] = useState(0);
  const raf = useRef(0);
  useEffect(() => {
    if (prefersReducedMotion() || target <= 0) {
      setV(target);
      return;
    }
    const start = performance.now();
    const D = 1600;
    const step = (now: number) => {
      const p = Math.min(1, (now - start) / D);
      setV(target * (1 - Math.pow(1 - p, 3)));
      if (p < 1) raf.current = requestAnimationFrame(step);
    };
    raf.current = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  useEffect(() => {
    // 数据刷新导致「现在」前移时，直接跟上，不重扫
    setV((cur) => (cur > 0 && Math.abs(cur - target) < 0.2 ? target : cur));
  }, [target]);
  return v;
}

export function SignalTimeline({
  data,
  selectedId,
  hoverId,
  onHover,
  onOpen,
  legend,
  range = 'today',
  onRange,
}: {
  data: TodaySignals | null;
  selectedId?: number | null;
  hoverId?: number | null;
  onHover?: (id: number | null) => void;
  onOpen: (id: number) => void;
  legend?: ReactNode;
  range?: SignalRange;
  onRange?: (r: SignalRange) => void;
}) {
  // 「今天」在上午很空：视图缩到 [00:00, max(现在 + 3h, 09:00)]，右侧未来区画斜纹
  const view = data ? timelineView(range, data.start, data.end, data.now) : null;
  const nowPos = data && view ? dayPosition(data.now, view.start, view.end) : 0;
  const head = useSweep(nowPos, `${range}:${data?.start ?? ''}`);
  const headLabel = view ? fmtHM(new Date(view.startMs + head * (view.endMs - view.startMs))) : '';
  const ticks = view ? rulerTicks(range === 'today' && view.zoomed ? 'zoom' : range, view.start, view.end) : [];
  const inner = ticks.filter((t) => t.pos > 0.001 && t.pos < 0.999);
  const [tip, setTip] = useState<{ x: number; y: number; title: string; sub: string } | null>(null);
  const title = SIGNAL_TITLE[range];
  const count = data ? data.tracks.reduce((n, t) => n + t.items.length, 0) : 0;
  const showTip = (el: HTMLElement, title: string, sub: string) => {
    const r = el.getBoundingClientRect();
    setTip({ x: Math.min(r.left, window.innerWidth - 340), y: r.bottom + 8, title, sub });
  };
  return (
    <section className="cw-timeline" aria-label={title}>
      <div className="cw-tl-head">
        <h2>{title}</h2>
        {data ? <span className="cw-tl-count cw-num" title="这个时间段里发布的条数（采集到的总数见信号流）">{count} 条发布</span> : null}
        {legend}
        {onRange ? (
          <>
            <span className="cw-grow" />
            <Segmented value={range} options={SIGNAL_RANGES} onChange={onRange} label="时间范围" />
          </>
        ) : null}
      </div>
      <div className="cw-tl-body">
        <div className="cw-tl-grid">
          <div className="cw-ruler">
            <span />
            <div className="cw-ruler-scale">
              {ticks.map((t) => (
                <span key={t.pos} className="cw-num" style={{ left: `${t.pos * 100}%` }}>
                  {t.label}
                </span>
              ))}
            </div>
          </div>
          {!data || !view ? (
            <div className="cw-tl-scan" aria-busy="true">
              <i />
            </div>
          ) : data.tracks.length === 0 ? (
            <div className="cw-tl-flat">
              <svg viewBox="0 0 400 40" preserveAspectRatio="none" aria-hidden>
                <line x1="0" x2="400" y1="20" y2="20" />
                <circle r="3" cy="20" cx="0" />
              </svg>
              <span>{range === 'today' ? '今天还没有采到内容' : '这段时间没有采到内容'}</span>
            </div>
          ) : (
            data.tracks.slice(0, 9).map((track) => (
              <div className="cw-track" key={track.platform}>
                <span className="cw-track-name" title={platformName(track.platform)}>
                  {platformName(track.platform)}
                </span>
                <div className="cw-lane">
                  {inner.map((t) => (
                    <i key={t.pos} className="cw-lane-tick" style={{ left: `${t.pos * 100}%` }} />
                  ))}
                  {nowPos < 0.999 ? <i className="cw-lane-future" style={{ left: `${nowPos * 100}%` }} /> : null}
                  {clusterClips(track.items, view.start, view.end).map((g) => {
                    if (g.items.length > 3) {
                      const lit = g.pos <= head + 0.002;
                      const ids = g.items.map((c) => c.id);
                      return (
                        <button
                          key={`g${g.items[0].id}`}
                          type="button"
                          className="cw-clip"
                          data-dense="true"
                          data-lit={lit ? 'true' : undefined}
                          data-selected={ids.includes(selectedId ?? -1) ? 'true' : ids.includes(hoverId ?? -1) ? 'hover' : undefined}
                          aria-label={`${g.items.length} 条`}
                          onClick={() => onOpen(g.items[0].id)}
                          onPointerEnter={(e) =>
                            showTip(e.currentTarget, `${g.items.length} 条：${g.items[0].title}`, `${platformName(track.platform)} · ${fmtHM(g.items[0].at)}–${fmtHM(g.items[g.items.length - 1].at)}`)
                          }
                          onPointerLeave={() => setTip(null)}
                          style={
                            {
                              left: `${g.pos * 100}%`,
                              width: `${Math.max(0.6, g.span * 100)}%`,
                              '--c': mediaKindColor(g.items[0].media_type),
                              '--o': Math.min(1, 0.45 + g.items.length / 40),
                            } as CSSProperties
                          }
                        >
                          <b className="cw-num">{g.items.length}</b>
                        </button>
                      );
                    }
                    return g.items.map((clip) => {
                      const pos = dayPosition(clip.at, view.start, view.end);
                      return (
                        <button
                          key={clip.id}
                          type="button"
                          className="cw-clip"
                          data-lit={pos <= head + 0.002 ? 'true' : undefined}
                          data-selected={clip.id === selectedId ? 'true' : clip.id === hoverId ? 'hover' : undefined}
                          aria-label={clip.title}
                          onClick={() => onOpen(clip.id)}
                          onPointerEnter={(e) => {
                            showTip(e.currentTarget, clip.title, `${clip.source && track.platform === 'web' ? clip.source : platformName(track.platform)} · ${fmtHM(clip.at)} 发布`);
                            onHover?.(clip.id);
                          }}
                          onPointerLeave={() => {
                            setTip(null);
                            onHover?.(null);
                          }}
                          style={
                            {
                              left: `${pos * 100}%`,
                              '--c': mediaKindColor(clip.media_type),
                              '--o': heatOpacity(clip.heat),
                            } as CSSProperties
                          }
                        />
                      );
                    });
                  })}
                </div>
              </div>
            ))
          )}
          {data && view ? (
            <div className="cw-playhead" style={{ left: `calc(var(--cw-track-w) + (100% - var(--cw-track-w)) * ${head})` }}>
              <span className="cw-num">{headLabel}</span>
            </div>
          ) : null}
        </div>
      </div>
      {tip ? (
        <div className="cw-tip" style={{ left: tip.x, top: tip.y }} role="tooltip">
          {tip.title}
          <small>{tip.sub}</small>
        </div>
      ) : null}
    </section>
  );
}

// ── 追踪词点阵、平台条 ──

export function DotMatrix({ dots, label }: { dots: number[]; label: string }) {
  return (
    <div>
      <div className="cw-dots" role="img" aria-label={label}>
        {dots.map((n, i) => (
          <i key={i} data-on={n > 0 ? 'true' : undefined} title={`${n} 条`} />
        ))}
      </div>
      <div className="cw-dots-axis cw-num">
        <span>-24h</span>
        <span>-18h</span>
        <span>-12h</span>
        <span>-6h</span>
        <span>现在</span>
      </div>
    </div>
  );
}

export function PlatformBars({ dist, accent = color.mg }: { dist: Record<string, number>; accent?: string }) {
  const rows = topPlatforms(dist, 6);
  const max = Math.max(1, ...rows.map(([, n]) => n));
  if (!rows.length) return <div className="cw-muted">还没有采到</div>;
  return (
    <div className="cw-plat-bars" style={{ '--c': accent } as CSSProperties}>
      {rows.map(([p, n]) => (
        <div key={p}>
          <span>{platformName(p)}</span>
          <s style={{ width: `${(n / max) * 100}%` }} />
          <b className="cw-num">{n}</b>
        </div>
      ))}
    </div>
  );
}

/** 共振矩阵列头缩写（列宽 40px） */
const RES_SHORT: Record<string, string> = { github: 'GH', hackernews: 'HN', hacker_news: 'HN', hn: 'HN', rss: '网页', web: '网页', bilibili: 'B站', youtube: 'YT', reddit: 'Rd', douyin: '抖音', xiaohongshu: '小红书', weibo: '微博', zhihu: '知乎' };

export function ResonanceTable({ data, onOpen }: { data: ResonanceMatrix; onOpen: (id: number) => void }) {
  if (!data.rows.length)
    return <EmptyInstrument compact kind="dark" title="近 48 小时没有跨平台的事件" reason="同一件事同时出现在两个以上平台（比如网页和 B站）时会在这里亮起。" />;
  // 侧栏只有 340px：按出现次数取前 4 个平台，其余省略，避免把侧栏撑出屏幕
  const hits = (p: string) => data.rows.filter((r) => r.cells[p]).length;
  const platforms = [...data.platforms].sort((a, b) => hits(b) - hits(a)).slice(0, 4);
  return (
    <div className="cw-res-wrap">
    <table className="cw-res">
      <thead>
        <tr>
          <th>主题</th>
          {platforms.map((p) => (
            <th key={p} title={platformName(p)}>{RES_SHORT[p] ?? platformName(p).slice(0, 4)}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {data.rows.map((r) => (
          <tr key={r.event_id}>
            <td className="cw-res-title" title={r.title}>
              {r.representative_id ? (
                <button type="button" className="cw-link-btn" onClick={() => onOpen(r.representative_id!)}>
                  {r.title}
                </button>
              ) : (
                r.title
              )}
            </td>
            {platforms.map((p) => (
              <td key={p}>
                <i className="cw-res-dot" data-on={r.cells[p] ? 'true' : undefined} title={`${r.cells[p] || 0} 条`} />
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
    </div>
  );
}

/** 带缺口的曲线：没有观测的时段断开，不画 0 */
export function GapSpark({ values, width = 140, height = 30, accent = color.rd, label }: { values: (number | null)[]; width?: number; height?: number; accent?: string; label: string }) {
  // 少于 4 次观测画不出趋势，两点斜线只会误导：统一写「观测 N 次」（评审 #3 1.2-3）
  const n = values.filter((v) => v !== null).length;
  if (n < 4) return <span className="cw-spark-empty cw-num">{n ? `观测 ${n} 次` : '观测不足'}</span>;
  const paths = gappedPaths(values, width, height);
  if (!paths.length) return <span className="cw-spark-empty">观测不足</span>;
  return (
    <svg className="cw-spark" width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={label} style={{ '--c': accent } as CSSProperties}>
      {paths.map((d, i) => (
        <path key={i} d={d} />
      ))}
    </svg>
  );
}

// ── 条目详情 ──

export function ItemDrawer({ id, onClose, onChanged }: { id: number | null; onClose: () => void; onChanged?: (id: number) => void }) {
  return (
    <Drawer
      open={id !== null}
      onClose={onClose}
      size={620}
      title={null}
      closable={false}
      destroyOnHidden
      className="cw-drawer"
      styles={{ body: { padding: 0 } }}
    >
      {id !== null ? <ItemDetailView id={id} compact onClose={onClose} onChanged={onChanged} /> : null}
    </Drawer>
  );
}

function BasisRow({ name, children }: { name: string; children: ReactNode }) {
  return (
    <div className="cw-basis-row">
      <span className="cw-muted">{name}</span>
      <div>{children}</div>
    </div>
  );
}

export function ItemDetailView({ id, compact, onClose, onChanged }: { id: number; compact?: boolean; onClose?: () => void; onChanged?: (id: number) => void }) {
  const [data, setData] = useState<ItemDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState('');

  const load = useCallback(async () => {
    try {
      setError(null);
      setData(await discoverApi.item(id));
    } catch (err) {
      setError(errText(err));
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  const act = async (key: string, fn: () => Promise<unknown>, ok?: string) => {
    setBusy(key);
    try {
      await fn();
      if (ok) message.success(ok);
      await load();
      onChanged?.(id);
    } catch (err) {
      message.error(errText(err));
    } finally {
      setBusy(null);
    }
  };

  if (error) return <div className="cw-detail"><div className="cw-error">{error}</div></div>;
  if (!data) return <div className="cw-detail cw-detail-loading"><Spin /></div>;

  const v = data.verdict_full;
  const c = mediaKindColor(data.media_type);
  const key = primarySeries(data.series);
  const series = key ? data.series[key].map((p) => p.value) : [];
  const cover = data.cover_asset_id ? mediaUrl(data.cover_asset_id, 'full') : null;

  const correction = (
    <div className="cw-correct">
      <div className="cw-muted">改成正确的结论</div>
      <div className="cw-correct-btns">
        {(['worth', 'watch', 'skip'] as Verdict[]).map((opt) => (
          <Button
            key={opt}
            variant={v.verdict === opt ? 'primary' : 'default'}
            onClick={() => act('verdict', () => discoverApi.setVerdict(id, opt, note), '已记下')}
          >
            {VERDICT_LABEL[opt]}
          </Button>
        ))}
      </div>
      <Input.TextArea value={note} onChange={(e) => setNote(e.target.value)} placeholder="为什么（可选）" rows={2} maxLength={500} />
      {v.user_verdict ? (
        <Button variant="ghost" onClick={() => act('verdict', () => discoverApi.setVerdict(id, null), '已恢复计算结论')}>
          恢复计算结论（{VERDICT_LABEL[v.computed || v.verdict]}）
        </Button>
      ) : null}
    </div>
  );

  return (
    <article className="cw-detail" style={{ '--c': c } as CSSProperties}>
      <header className="cw-detail-head">
        <div className="cw-detail-actions">
          {compact ? (
            <Link className="cw-btn" data-variant="ghost" href={`/items/${id}`} aria-label="展开为独立页">
              <Maximize2 size={15} />
              独立页
            </Link>
          ) : null}
          <a className="cw-btn" data-variant="ghost" href={data.url} target="_blank" rel="noreferrer">
            <ExternalLink size={15} />
            原文
          </a>
          <Link
            className="cw-btn"
            data-variant="ghost"
            href={`/runs?topic=${encodeURIComponent(data.title)}&content=${id}`}
            title="以这条内容为起点发起选题研究"
          >
            <Workflow size={15} />
            选题研究
          </Link>
          <Link className="cw-btn" data-variant="ghost" href={`/projects/new?source=content:${id}`} title="以这条内容为主来源新建项目">
            做成项目
          </Link>
          <BreakdownButton target={{ content_id: id }} />
          <FeishuButton type="content" id={id} />
          {onClose ? (
            <Button variant="ghost" onClick={onClose}>
              关闭
            </Button>
          ) : null}
        </div>
        <section className="cw-conclusion" style={{ '--v': VERDICT_COLOR[v.verdict] } as CSSProperties}>
          <div className="cw-conclusion-top">
            <VerdictMark verdict={v.verdict} user={Boolean(v.user_verdict)} />
            <Popover content={correction} trigger="click" placement="bottomRight">
              <button type="button" className="cw-link-btn">不对</button>
            </Popover>
          </div>
          <p className="cw-conclusion-reason">{v.reason}</p>
          {v.user_note ? <p className="cw-muted">你的理由：{v.user_note}</p> : null}
          <div className="cw-basis">
            <BasisRow name="热度">
              {v.basis.heat.state ? (
                <span className="cw-muted">{v.basis.heat.state}</span>
              ) : (
                <>
                  {v.basis.heat.metric ? <span>{METRIC_LABEL[v.basis.heat.metric] || v.basis.heat.metric} <b className="cw-num">{compactNumber(v.basis.heat.value)}</b></span> : null}
                  {v.basis.heat.rank ? <span>上榜第 <b className="cw-num">{v.basis.heat.rank}</b></span> : null}
                  {v.basis.heat.growth ? <span className="cw-num cw-up">+{compactNumber(v.basis.heat.growth.last - v.basis.heat.growth.first)} / {Math.round(v.basis.heat.growth.hours)}h</span> : null}
                </>
              )}
            </BasisRow>
            <BasisRow name="时机">
              {v.basis.timing.age_hours !== undefined ? <span>发布 <b className="cw-num">{v.basis.timing.age_hours < 48 ? `${Math.round(v.basis.timing.age_hours)} 小时` : `${Math.round(v.basis.timing.age_hours / 24)} 天`}</b></span> : null}
              <StatusTag status={v.basis.timing.topic_status} />
            </BasisRow>
            <BasisRow name="同题">
              {v.basis.same_topic.event_id ? (
                <span>
                  同一事件 <b className="cw-num">{v.basis.same_topic.members}</b> 条 ·{' '}
                  {Array.from(new Set(v.basis.same_topic.platforms)).map(platformName).join('、')}
                </span>
              ) : (
                <span className="cw-muted">未归入事件</span>
              )}
            </BasisRow>
            <BasisRow name="和你相关">
              {v.basis.relevance.keyword_hits.length ? <span>追踪词「{v.basis.relevance.keyword_hits.join('、')}」</span> : null}
              {v.basis.relevance.related_favorites ? <span>相关收藏 <b className="cw-num">{v.basis.relevance.related_favorites}</b></span> : null}
              {!v.basis.relevance.keyword_hits.length && !v.basis.relevance.related_favorites ? <span className="cw-muted">无</span> : null}
            </BasisRow>
            <BasisRow name="风险">
              {v.basis.risk.rule_hits.length ? <span className="cw-bad">命中规则：{v.basis.risk.rule_hits.join('、')}</span> : null}
              {v.basis.risk.score !== null ? <span>风险分 <b className="cw-num">{Math.round(v.basis.risk.score)}</b></span> : <span className="cw-muted">未分析，只看规则：{v.basis.risk.rule_hits.length ? '有风险' : '无'}</span>}
            </BasisRow>
            <BasisRow name="内容质量">
              {v.basis.quality !== null ? <b className="cw-num">{Math.round(v.basis.quality)}</b> : <span className="cw-muted">未分析</span>}
            </BasisRow>
          </div>
          {v.missing.length ? (
            <div className="cw-missing">
              {v.missing.map((m) => (
                <span key={m}>{m}</span>
              ))}
            </div>
          ) : null}
          <details className="cw-calc">
            <summary>计算明细</summary>
            <p className="cw-muted">{v.detail.formula}</p>
            <ul>
              {v.detail.scored.map((s, i) => (
                <li key={i}>
                  <span>{BASIS_LABEL[s.basis] || s.basis}</span>
                  <span>{s.why}</span>
                  <b className="cw-num">{s.points > 0 ? `+${s.points}` : s.points}</b>
                </li>
              ))}
              <li>
                <span>合计</span>
                <span />
                <b className="cw-num">{v.detail.points}</b>
              </li>
            </ul>
          </details>
        </section>
      </header>

      <section className="cw-detail-body">
        {cover || data.media_type === 'video' ? (
          <div className="cw-detail-cover">
            <Cover src={cover} title={data.title} color={data.cover_color} orientation={data.orientation} kind={data.media_type} badge={formatDuration(data.duration)} />
          </div>
        ) : null}
        <h2 className="cw-detail-title">{data.title}</h2>
        <div className="cw-item-meta">
          <span className="cw-plat">{platformName(data.platform)}</span>
          {data.author ? (data.author_url ? <a href={data.author_url} target="_blank" rel="noreferrer">{data.author}</a> : <span>{data.author}</span>) : null}
          <span>发布 {data.published_at ? new Date(data.published_at).toLocaleString('zh-CN') : '时间未知'}</span>
          <span>采集 {relativeTime(data.crawled_at)}</span>
        </div>
        <div className="cw-detail-tools">
          <Button
            icon={<ThumbsUp size={15} />}
            variant={data.feedback === 'useful' ? 'primary' : 'default'}
            disabled={busy === 'fb'}
            onClick={() => act('fb', () => discoverApi.setFeedback(id, data.feedback === 'useful' ? null : 'useful'))}
          >
            有用
          </Button>
          <Button
            icon={<ThumbsDown size={15} />}
            variant={data.feedback === 'not_interested' ? 'primary' : 'default'}
            disabled={busy === 'fb'}
            onClick={() => act('fb', () => discoverApi.setFeedback(id, data.feedback === 'not_interested' ? null : 'not_interested'))}
          >
            不感兴趣
          </Button>
          <span className="cw-grow" />
          <Button
            icon={<Bookmark size={15} />}
            variant={data.is_favorited ? 'primary' : 'default'}
            disabled={busy === 'fav' || data.is_favorited}
            onClick={() =>
              act(
                'fav',
                () => favoritesApi.create({ target_type: 'content', target_id: id, title: data.title, url: data.url, source_name: data.source_name }),
                data.analysis_level === 'full' ? '已收进灵感库' : '已收进灵感库，正在补分析',
              )
            }
          >
            {data.is_favorited ? '已收藏' : '收藏'}
          </Button>
        </div>

        <h3 className="cw-detail-h">指标与观测</h3>
        <div className="cw-detail-metrics">
          <MetricScope metric={data.metric} accent={c} />
          {key ? <Sparkline values={series} label={`${METRIC_LABEL[key] || key}观测曲线`} color={c} width={220} height={40} /> : <span className="cw-spark-empty">{data.metric.state || '暂无历史观测'}</span>}
        </div>

        <h3 className="cw-detail-h">角度</h3>
        {data.analysis && data.analysis.angles.length ? (
          <ol className="cw-angles">
            {data.analysis.angles.map((a, i) => (
              <li key={i}>
                <b>{a.title}</b>
                {a.detail ? <p className="cw-muted">{a.detail}</p> : null}
                <Link href={`/projects/new?source=content:${data.event?.representative_id || id}&theme=${encodeURIComponent(a.title)}`} className="cw-link-btn">用于新项目</Link>
              </li>
            ))}
          </ol>
        ) : (
          <div className="cw-angles-empty">
            <span className="cw-muted">{data.analysis_level === 'full' ? '这次分析没有给出角度' : '还没有完整分析'}</span>
            {data.analysis_level !== 'full' ? (
              <Button icon={<Sparkles size={15} />} variant="primary" disabled={busy === 'analyze'} onClick={() => act('analyze', () => discoverApi.analyze(id), '分析完成')}>
                {busy === 'analyze' ? '分析中…' : '分析并给角度'}
              </Button>
            ) : null}
          </div>
        )}
        {data.analysis?.inherited_from ? <p className="cw-muted">继承自同一事件的代表条目 #{data.analysis.inherited_from}</p> : null}
        {data.analysis?.summary ? <p className="cw-detail-summary">{data.analysis.summary}</p> : null}

        {data.event ? (
          <>
            <h3 className="cw-detail-h">
              同一事件的其他来源 <small className="cw-muted">{data.event.others.length} 条</small>
              <span className="cw-grow" />
              <Button variant="ghost" icon={<Unlink size={14} />} disabled={busy === 'leave'} onClick={() => act('leave', () => discoverApi.leaveEvent(id), '已移出此事件')}>
                移出此事件
              </Button>
            </h3>
            <ul className="cw-others">
              {data.event.others.map((o) => (
                <li key={o.id} style={{ '--c': mediaKindColor(o.media_type) } as CSSProperties}>
                  <i />
                  <span className="cw-plat">{platformName(o.platform)}</span>
                  <a href={o.url} target="_blank" rel="noreferrer">{o.title}</a>
                  <span className="cw-muted cw-num">{relativeTime(o.published_at)}</span>
                </li>
              ))}
            </ul>
          </>
        ) : null}

        {data.dossiers.length ? (
          <>
            <h3 className="cw-detail-h">所属专题</h3>
            <div className="cw-chips">
              {data.dossiers.map((d) => (
                <Link key={d.id} className="cw-chip" href={`/dossiers/${d.id}`}>{d.title}</Link>
              ))}
            </div>
          </>
        ) : null}

        <h3 className="cw-detail-h">原文</h3>
        <div className="cw-reader">
          {data.raw_content || data.summary_full ? (
            (data.raw_content || data.summary_full || '').split(/\n{2,}/).slice(0, compact ? 8 : 200).map((p, i) => <p key={i}>{p}</p>)
          ) : (
            <p className="cw-muted">没有正文，点「原文」打开来源页面。</p>
          )}
          {compact && (data.raw_content || '').split(/\n{2,}/).length > 8 ? <Link href={`/items/${id}`} className="cw-link-btn">在独立页阅读全文</Link> : null}
        </div>

        <CommentsSection id={id} state={data.comment_state} />

        <h3 className="cw-detail-h">经历</h3>
        <ol className="cw-journey">
          {data.journey.length === 0 ? <li className="cw-muted">没有记录</li> : null}
          {data.journey.map((j) => (
            <li key={j.id}>
              <span className="cw-journey-stage">{JOURNEY_LABEL[j.stage] || j.stage}</span>
              <span>{j.summary}</span>
              <span className="cw-muted cw-num">{new Date(j.at).toLocaleString('zh-CN', { hour12: false })}</span>
            </li>
          ))}
        </ol>
      </section>
    </article>
  );
}

export { MEDIA_LABEL, STATUS_LABEL, platformName as platformLabel };


const COMMENT_STATE_TEXT: Record<string, string> = {
  none: '未采集',
  collected: '已采集',
  unavailable: '无评论来源',
  failed: '采集失败',
};

/** 评论折叠区（3.5）：默认收起；展开后按点赞排序，可「加载评论」「总结评论」。 */
export function CommentsSection({ id, state }: { id: number; state: string }) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<CommentList | null>(null);
  const [busy, setBusy] = useState<'load' | 'digest' | null>(null);
  const [focus, setFocus] = useState<number[]>([]);

  useEffect(() => {
    setData(null);
    setFocus([]);
    if (!open) return;
    discoverApi
      .comments(id)
      .then(setData)
      .catch(() => setData(null));
  }, [id, open]);

  const load = async (refresh: boolean) => {
    setBusy('load');
    try {
      const r = await discoverApi.loadComments(id, refresh);
      setData(r);
      if (r.error) message.warning(`评论采集失败：${r.error}`);
    } catch (err) {
      message.error(err instanceof Error ? err.message : '请求失败');
    } finally {
      setBusy(null);
    }
  };
  const digest = async () => {
    setBusy('digest');
    try {
      const d = await discoverApi.digestComments(id);
      setData((prev) => (prev ? { ...prev, digest: d } : prev));
    } catch (err) {
      message.error(err instanceof Error ? err.message : '请求失败');
    } finally {
      setBusy(null);
    }
  };

  const st = data?.state || state;
  return (
    <section className="cw-comments">
      <h3 className="cw-detail-h">
        <button type="button" className="cw-link-btn" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
          {open ? '▾' : '▸'} 评论
        </button>
        <span className="cw-muted" style={{ fontWeight: 400, fontSize: 12 }}>
          {COMMENT_STATE_TEXT[st] || st}
          {data?.items.length ? ` · ${data.items.length} 条` : ''}
        </span>
      </h3>
      {open ? (
        <>
          <div className="cw-row" style={{ marginBottom: 8 }}>
            {st !== 'unavailable' ? (
              <Button onClick={() => load(st === 'collected' || st === 'failed')} disabled={busy !== null}>
                {busy === 'load' ? '加载中…' : st === 'collected' ? '刷新评论' : '加载评论'}
              </Button>
            ) : (
              <span className="cw-muted">这个来源没有评论接口</span>
            )}
            {data?.items.length ? (
              <Button icon={<Sparkles size={14} />} onClick={digest} disabled={busy !== null}>
                {busy === 'digest' ? '总结中…' : data.digest ? '重新总结' : '总结评论'}
              </Button>
            ) : null}
          </div>
          {data?.digest ? (
            <div className="cw-comment-digest">
              <div className="cw-muted" style={{ fontSize: 12 }}>基于 {data.digest.based_on} 条评论</div>
              <ul>
                {data.digest.points.map((p, i) => (
                  <li key={i}>
                    <button type="button" className="cw-link-btn" onClick={() => setFocus(p.comment_ids)} title="高亮依据的评论">
                      {p.text}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {data && data.items.length === 0 && st === 'collected' ? <p className="cw-muted">没有评论</p> : null}
          <ol className="cw-comment-list">
            {data?.items.map((c) => (
              <li key={c.id} data-focus={focus.includes(c.id) ? 'true' : undefined}>
                <div className="cw-comment-meta">
                  <span>{c.author || '匿名'}</span>
                  <span className="cw-num cw-muted">{c.likes != null ? `${compactNumber(c.likes)} 赞` : ''}</span>
                  {c.replies ? <span className="cw-num cw-muted">{c.replies} 回复</span> : null}
                </div>
                <p>{c.text}</p>
              </li>
            ))}
          </ol>
        </>
      ) : null}
    </section>
  );
}
