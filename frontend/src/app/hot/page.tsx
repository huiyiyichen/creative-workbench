'use client';

/**
 * 热点（改造方案 5.2）：热榜 / 共振 / 升温 / 追踪词。
 * 原趋势雷达（/trending）的热榜与共振、原趋势追踪（/trends）与母题配置（/my-topics/config）合并到这里。
 */

import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { Select, Switch, message } from 'antd';
import { Plus, RefreshCw, Star } from 'lucide-react';
import { Suspense, useCallback, useEffect, useMemo, useState, type CSSProperties } from 'react';
import { Button, Card, CwPage, Segmented, TopBar } from '@/design/components';
import { EmptyInstrument, Instrument, ScanSkeleton, StatusLamp } from '@/design/instrument';
import { PhaseChart } from '@/design/phase-chart';
import { GapSpark, ItemDrawer, PlatformBars, StatusTag, VerdictMark, platformName } from '@/design/discover';
import { color } from '@/design/tokens';
import { motherTopicsApi } from '@/lib/api/_mother-topics';
import { collectionApi, type PlatformInfo } from '@/lib/api/_collection';
import { discoverApi, type RisingBoard, type TopicStatus, type WatchTermCurve } from '@/lib/api/_discover';
import { trendingApi } from '@/lib/api/_trending';
import { INTERVAL_OPTIONS, intervalLabel, relativeTime } from '@/lib/collection';
import { bucketSeries, topPlatforms } from '@/lib/discover';
import type { CrossPlatformCluster, MotherTopic, TrendingItem, TrendingSource } from '@/types/trending';
import { AddSourceModal } from '../sources/_parts';
import { RemoveTermButton, WatchTermInput } from '@/design/watch-terms';

type Tab = 'list' | 'resonance' | 'rising' | 'terms';
const TABS: { id: Tab; label: string }[] = [
  { id: 'list', label: '热榜' },
  { id: 'resonance', label: '共振' },
  { id: 'rising', label: '升温' },
  { id: 'terms', label: '追踪词' },
];

const HOT_SOURCE_LABEL: Record<string, string> = {
  baidu: '百度热搜',
  bilibili: 'B站热门',
  douban: '豆瓣',
  douyin: '抖音热榜',
  weibo: '微博热搜',
  zhihu: '知乎热榜',
  toutiao: '今日头条',
  xiaohongshu: '小红书',
  thepaper: '澎湃新闻',
  '36kr': '36氪',
  ithome: 'IT之家',
  sspai: '少数派',
  juejin: '掘金',
  github: 'GitHub Trending',
  hackernews: 'Hacker News',
  producthunt: 'Product Hunt',
  v2ex: 'V2EX',
  xueqiu: '雪球',
  wallstreetcn: '华尔街见闻',
  cls: '财联社',
  xiaoyuzhou: '小宇宙',
  eastmoney: '东方财富',
  xyzrank: '播客榜',
  hupu: '虎扑',
  tieba: '百度贴吧',
  netease: '网易新闻',
  sohu: '搜狐',
  kr36: '36氪',
};
const HOT_CATEGORY_LABEL: Record<string, string> = { hot: '综合', tech: '科技', finance: '财经', podcast: '播客', news: '新闻', video: '视频', dev: '开发' };

function errText(err: unknown): string {
  return err instanceof Error ? err.message : '请求失败';
}

// ── 热榜 ──

function HotList() {
  const [sources, setSources] = useState<TrendingSource[]>([]);
  const [items, setItems] = useState<TrendingItem[] | null>(null);
  const [category, setCategory] = useState<string>('');
  const [syncing, setSyncing] = useState(false);

  const load = useCallback(async () => {
    const [s, i] = await Promise.all([trendingApi.listSources(), trendingApi.list({ category: category || undefined, limit: 500 })]);
    setSources(s);
    setItems(i);
  }, [category]);

  useEffect(() => {
    load().catch((err) => message.error(errText(err)));
  }, [load]);

  const bySource = useMemo(() => {
    const map = new Map<string, TrendingItem[]>();
    for (const it of items || []) {
      const arr = map.get(it.source) || [];
      arr.push(it);
      map.set(it.source, arr);
    }
    for (const arr of map.values()) arr.sort((a, b) => a.rank - b.rank);
    return map;
  }, [items]);

  const categories = useMemo(() => Array.from(new Set(sources.map((s) => s.category))), [sources]);
  const label = (src: string) => HOT_SOURCE_LABEL[src] || src;
  const synced = (src: string) => sources.find((s) => s.source === src)?.last_synced;
  const [mountedAt] = useState(() => Date.now());
  const stale = (ts: string | null | undefined) => !ts || mountedAt - new Date(ts).getTime() > 3 * 3600000;

  const syncAll = async () => {
    setSyncing(true);
    try {
      await trendingApi.syncAll();
      await load();
      message.success('已同步各平台热榜');
    } catch (err) {
      message.error(errText(err));
    } finally {
      setSyncing(false);
    }
  };

  return (
    <>
      <div className="cw-filters">
        <Segmented
          label="分类"
          value={category}
          onChange={setCategory}
          options={[{ value: '', label: '全部' }, ...categories.map((c) => ({ value: c, label: HOT_CATEGORY_LABEL[c] || c }))]}
        />
        <span className="cw-grow" />
        <Button icon={<RefreshCw size={15} />} onClick={syncAll} disabled={syncing}>
          {syncing ? '同步中…' : '手动同步'}
        </Button>
      </div>
      {!items ? (
        <ScanSkeleton shape="columns" height={300} />
      ) : bySource.size === 0 ? (
        <EmptyInstrument
          kind="unplugged"
          title="还没有热榜数据"
          reason="热榜每小时从各平台抓一次；第一次可以手动同步。"
          actions={
            <Button variant="primary" icon={<RefreshCw size={15} />} onClick={syncAll} disabled={syncing}>
              {syncing ? '同步中…' : '现在同步'}
            </Button>
          }
        />
      ) : (
        <div className="cw-hotgrid cw-stagger">
          {Array.from(bySource.entries()).map(([src, rows]) => {
            return (
              <Instrument
                key={src}
                className="cw-hotcol"
                title={label(src)}
                extra={
                  // 正常同步只写时间，不再每列一个绿灯；超过 3 小时没同步才亮黄灯（评审 #3 1.3）
                  stale(synced(src)) ? (
                    <StatusLamp tone={synced(src) ? 'warn' : 'off'} label={<span className="cw-num">{synced(src) ? relativeTime(synced(src)) : '未同步'}</span>} />
                  ) : (
                    <small className="cw-muted cw-num">{relativeTime(synced(src))}</small>
                  )
                }
              >
                <ol>
                  {rows.slice(0, 15).map((r) => (
                    <li key={r.id} data-top={r.rank <= 3 ? 'true' : undefined}>
                      <b className="cw-num">{r.rank}</b>
                      <a href={r.url} target="_blank" rel="noreferrer" title={r.title}>
                        {r.title}
                      </a>
                      <small className="cw-num">{r.hot_value && r.hot_value_raw && !/^0(\.0+)?$/.test(r.hot_value_raw) ? hotText(r.hot_value_raw) : ''}</small>
                    </li>
                  ))}
                </ol>
              </Instrument>
            );
          })}
        </div>
      )}
    </>
  );
}

// ── 共振 ──

function Resonance() {
  const [min, setMin] = useState(2);
  const [clusters, setClusters] = useState<CrossPlatformCluster[] | null>(null);

  useEffect(() => {
    setClusters(null);
    trendingApi
      .crossPlatform({ min_resonance: min, limit: 40 })
      .then((r) => setClusters(r.clusters))
      .catch((err) => {
        message.error(errText(err));
        setClusters([]);
      });
  }, [min]);

  return (
    <>
      <div className="cw-filters">
        <span className="cw-muted">同一事件同时上榜的平台数</span>
        <Segmented
          label="最低平台数"
          value={String(min)}
          onChange={(v) => setMin(Number(v))}
          options={[2, 3, 4].map((n) => ({
            value: String(n),
            label: `≥ ${n}`,
          }))}
        />
      </div>
      {!clusters ? (
        <ScanSkeleton height={240} />
      ) : clusters.length === 0 ? (
        <EmptyInstrument
          kind="dark"
          title={`现在没有 ${min} 个平台以上同时上榜的话题`}
          reason="各平台热榜里同一件事被归到一起后会出现在这里。"
          actions={min > 2 ? <Button onClick={() => setMin(2)}>放宽到 2 个平台</Button> : undefined}
        />
      ) : (
        <ul className="cw-rows cw-stagger">
          {clusters.map((c) => (
            <li key={c.topic} className="cw-resrow">
              <div className="cw-rise-title">
                <b>{c.topic}</b>
                <small>{c.keywords.slice(0, 5).join(' · ')}</small>
              </div>
              <div>
                <b className="cw-num" style={{ fontSize: 18 }}>
                  {c.resonance}
                </b>{' '}
                <span className="cw-muted">平台</span>
              </div>
              <div className="cw-res-plats">
                {c.source_items.slice(0, 6).map((s, i) => (
                  <a key={i} href={s.url} target="_blank" rel="noreferrer" title={s.title}>
                    {s.source_label} <span className="cw-num">#{s.rank}</span>
                  </a>
                ))}
              </div>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

// ── 升温 ──

const STATUS_FILTERS: { value: '' | TopicStatus; label: string }[] = [
  { value: '', label: '全部' },
  { value: 'rising', label: '升温' },
  { value: 'new', label: '新出现' },
  { value: 'steady', label: '持续' },
  { value: 'peak', label: '见顶' },
  { value: 'cooling', label: '降温' },
];

function Rising({ onOpen }: { onOpen: (id: number) => void }) {
  const router = useRouter();
  const [status, setStatus] = useState<'' | TopicStatus>('');
  const [board, setBoard] = useState<RisingBoard | null>(null);
  const [now, setNow] = useState(0);
  useEffect(() => setNow(Date.now()), [board]);

  const load = useCallback(() => {
    discoverApi
      .rising({ status: status || undefined })
      .then(setBoard)
      .catch((err) => message.error(errText(err)));
  }, [status]);

  useEffect(() => {
    load();
  }, [load]);

  const follow = async (eventId: number | null, watchId: number | null) => {
    try {
      const d = await discoverApi.follow({
        event_id: eventId ?? undefined,
        watch_source_id: watchId ?? undefined,
      });
      message.success('已关注，进入专题');
      router.push(`/dossiers/${d.id}`);
    } catch (err) {
      message.error(errText(err));
    }
  };

  return (
    <>
      <div className="cw-filters">
        <span className="cw-grow" />
        <span className="cw-muted">{board?.computed_at ? `每小时计算 · ${relativeTime(board.computed_at)}` : ''}</span>
      </div>
      {!board ? (
        <ScanSkeleton shape="scan" height={280} />
      ) : board.items.length === 0 && !status && board.hot_rising?.length ? (
        <Card title="热榜升温" extra={<small className="cw-muted">话题信号攒够两次观测前，先看各热榜最近两批的变化</small>}>
          <ul className="cw-rows">
            {board.hot_rising.map((r) => (
              <li key={`${r.source}-${r.title}`} className="cw-hotrise">
                <span className="cw-hotrise-tag" data-kind={r.trend}>
                  {r.trend === 'new' ? '新上榜' : r.rank_delta ? `↑${r.rank_delta}` : '上升'}
                </span>
                <a href={r.url} target="_blank" rel="noreferrer" className="cw-hotrise-title">
                  {r.title}
                </a>
                <span className="cw-muted">{HOT_SOURCE_LABEL[r.source] || r.source}</span>
                <span className="cw-num cw-muted">第 {r.rank} 名</span>
                <span className="cw-num cw-muted">{r.hot_value_raw}</span>
              </li>
            ))}
          </ul>
        </Card>
      ) : board.items.length === 0 ? (
        <EmptyInstrument
          kind="flat"
          title={status ? `现在没有「${STATUS_FILTERS.find((f) => f.value === status)?.label}」的话题` : '还没有话题信号'}
          reason={`话题信号每小时计算一次${board.computed_at ? `，上次 ${relativeTime(board.computed_at)}` : ''}；一个话题至少要有两次观测才能判断升降。`}
          actions={
            <>
              {status ? <Button onClick={() => setStatus('')}>看全部</Button> : null}
              <Link className="cw-btn" data-variant="primary" href="/hot?tab=list">
                看热榜
              </Link>
              <Link className="cw-link-btn" href="/hot?tab=terms">
                添加追踪词
              </Link>
            </>
          }
        />
      ) : (
        <>
          <Instrument
            title="热度相位"
            legend={
              <span className="cw-muted" style={{ fontSize: 12 }}>
                横轴：出现多久 · 纵轴：最近的变化 · 圆点大小：条数
              </span>
            }
          >
            <PhaseChart
              rows={board.items}
              now={now}
              active={status}
              onPick={setStatus}
              onOpen={(id) => {
                const t = board.items.find((x) => x.id === id);
                if (t?.representative) onOpen(t.representative.id);
              }}
            />
          </Instrument>
          <ul className="cw-rows cw-stagger" style={{ marginTop: 16 }}>
            {board.items.map((t) => (
              <li key={t.id} className="cw-rise">
                <div className="cw-rise-title">
                  {t.dossier_id ? (
                    <Link href={`/dossiers/${t.dossier_id}`}>
                      <b>{t.title}</b>
                    </Link>
                  ) : (
                    <b>{t.title}</b>
                  )}
                  <small>
                    {t.kind === 'watch_term' ? '追踪词' : '事件'} · {t.content_count} 条 · {t.source_count ?? 0} 个信源
                    {t.first_platform ? ` · 最先出现在${platformName(t.first_platform)}` : ''}
                  </small>
                </div>
                <GapSpark values={bucketSeries(t.series, 3)} label={`${t.title} 72 小时信号`} accent={t.status === 'cooling' ? color.bl : color.rd} />
                <StatusTag status={t.status} />
                <div className="cw-rise-rep">
                  <div className="cw-rise-plats">
                    {topPlatforms(t.platforms, 4).map(([p, n]) => (
                      <span key={p}>
                        {platformName(p)} <b className="cw-num">{n}</b>
                      </span>
                    ))}
                  </div>
                  {t.representative && !sameTitle(t.representative.title, t.title) ? (
                    <button type="button" className="cw-link-btn" onClick={() => onOpen(t.representative!.id)} title={t.representative.title}>
                      {t.representative.title}
                    </button>
                  ) : null}
                </div>
                <div
                  style={{
                    display: 'flex',
                    gap: 6,
                    alignItems: 'center',
                    justifyContent: 'flex-end',
                  }}
                >
                  {t.representative ? <VerdictMark verdict={t.representative.verdict} size="small" /> : null}
                  {t.dossier_id ? null : (
                    <Button variant="ghost" icon={<Star size={14} />} onClick={() => follow(t.event_id, t.watch_source_id)}>
                      关注
                    </Button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
    </>
  );
}

// ── 追踪词 ──

function WatchTerms() {
  const [items, setItems] = useState<WatchTermCurve[] | null>(null);
  const [split, setSplit] = useState(false);
  const [adding, setAdding] = useState(false);
  const [platforms, setPlatforms] = useState<PlatformInfo[]>([]);
  const [presets, setPresets] = useState<MotherTopic[]>([]);

  const load = useCallback(() => {
    discoverApi
      .watchTerms()
      .then((r) => setItems(r.items))
      .catch((err) => message.error(errText(err)));
  }, []);

  useEffect(() => {
    load();
    collectionApi
      .platforms()
      .then((r) => setPlatforms(r.items))
      .catch(() => undefined);
    motherTopicsApi
      .list(false, 'all')
      .then(setPresets)
      .catch(() => setPresets([]));
  }, [load]);

  const existing = new Set((items || []).map((t) => t.term));
  const presetWords = Array.from(new Set(presets.flatMap((p) => p.keywords)))
    .filter((k) => !existing.has(k))
    .slice(0, 24);

  const addPreset = async (word: string) => {
    try {
      const rec = await collectionApi.recognize(word);
      await collectionApi.createSource({
        ...rec,
        kind: 'keyword',
        query: word,
        name: word,
        sync_now: false,
      });
      message.success(`已添加追踪词「${word}」`);
      load();
    } catch (err) {
      message.error(errText(err));
    }
  };

  const update = async (id: number, body: { enabled?: boolean; interval_minutes?: number }) => {
    try {
      await collectionApi.updateSource(id, body);
      load();
    } catch (err) {
      message.error(errText(err));
    }
  };

  return (
    <>
      <div className="cw-filters">
        <WatchTermInput
          onAdded={(w) => {
            message.success(`已添加追踪词「${w}」，下一轮采集出数`);
            load();
          }}
        />
        <Button icon={<Plus size={15} />} onClick={() => setAdding(true)} title="指定平台、频率等">
          高级添加
        </Button>
        <span className="cw-muted">按平台拆开</span>
        <Switch size="small" checked={split} onChange={setSplit} />
      </div>
      {!items ? (
        <ScanSkeleton height={200} />
      ) : items.length === 0 ? (
        <EmptyInstrument
          kind="dark"
          title="还没有追踪词"
          reason="追一个关键词（比如一个产品名），各平台 24 小时里出现几次会画成点阵，涨起来会进「升温」。"
          actions={
            <Button variant="primary" icon={<Plus size={15} />} onClick={() => setAdding(true)}>
              添加追踪词
            </Button>
          }
        />
      ) : (
        <ul className="cw-rows">
          {items.map((t) => (
            <li
              key={t.source_id}
              id={`term-${t.source_id}`}
              className="cw-rise"
              style={{
                gridTemplateColumns: 'minmax(0,1.2fr) 220px 76px minmax(0,1fr) 210px',
              }}
            >
              <div className="cw-rise-title">
                <b>{t.term}</b>
                <small>
                  {t.platforms.length ? t.platforms.map(platformName).join('、') : '全部可搜索平台'} · 上次同步 {relativeTime(t.last_sync_at)}
                </small>
              </div>
              {split && t.trend ? (
                <PlatformBars dist={t.trend.platforms} accent={color.mg} />
              ) : (
                <GapSpark values={bucketSeries(t.trend?.series || [], 3)} width={210} label={`${t.term} 72 小时曲线`} accent={color.mg} />
              )}
              <StatusTag status={t.trend?.status} />
              <div className="cw-rise-plats">
                {t.trend ? (
                  <>
                    <span>
                      近 24 小时信号 <b className="cw-num">{t.trend.signal?.toFixed(1) ?? '—'}</b>
                    </span>
                    <span>
                      7 天 <b className="cw-num">{t.trend.content_count}</b> 条
                    </span>
                  </>
                ) : (
                  <span className="cw-muted">还没有计算</span>
                )}
              </div>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  justifyContent: 'flex-end',
                }}
              >
                <Select
                  size="small"
                  value={t.interval_minutes}
                  style={{ width: 104 }}
                  onChange={(v) => update(t.source_id, { interval_minutes: v })}
                  options={INTERVAL_OPTIONS.map((m) => ({
                    value: m,
                    label: intervalLabel(m),
                  }))}
                />
                <Switch size="small" checked={t.enabled} onChange={(v) => update(t.source_id, { enabled: v })} aria-label={t.enabled ? '暂停追踪' : '恢复追踪'} />
                <RemoveTermButton
                  sourceId={t.source_id}
                  term={t.term}
                  onRemoved={() => {
                    message.success(`已删除追踪词「${t.term}」`);
                    load();
                  }}
                />
              </div>
            </li>
          ))}
        </ul>
      )}
      {presetWords.length ? (
        <Card title="预设" extra={<small className="cw-muted">原系统母题模板库，点一下添加</small>} className="cw-report-sec">
          <div className="cw-chips">
            {presetWords.map((w) => (
              <button key={w} type="button" className="cw-chip" onClick={() => addPreset(w)}>
                + {w}
              </button>
            ))}
          </div>
        </Card>
      ) : null}
      <AddSourceModal
        open={adding}
        onClose={() => setAdding(false)}
        onAdded={(m) => {
          setAdding(false);
          message.success(m);
          load();
        }}
        searchable={platforms.filter((p) => p.capabilities.search)}
      />
    </>
  );
}

function HotPage() {
  const router = useRouter();
  const params = useSearchParams();
  const tab = (TABS.find((t) => t.id === params.get('tab'))?.id || 'list') as Tab;
  const [openId, setOpenId] = useState<number | null>(null);

  return (
    <CwPage>
      <TopBar title="热点">
        <Segmented
          label="热点分页"
          value={tab}
          onChange={(t) => router.replace(`/hot?tab=${t}`)}
          options={TABS.map((t) => ({ value: t.id, label: t.label }))}
        />
      </TopBar>
      <div style={{ '--c': color.rd } as CSSProperties}>
        {tab === 'list' ? <HotList /> : null}
        {tab === 'resonance' ? <Resonance /> : null}
        {tab === 'rising' ? <Rising onOpen={setOpenId} /> : null}
        {tab === 'terms' ? <WatchTerms /> : null}
      </div>
      <ItemDrawer id={openId} onClose={() => setOpenId(null)} />
    </CwPage>
  );
}

export default function Page() {
  return (
    <Suspense fallback={null}>
      <HotPage />
    </Suspense>
  );
}

/** 代表条目标题和话题标题基本一样时不再复述（评审 #3 1.2-4） */
function sameTitle(a: string | null | undefined, b: string | null | undefined): boolean {
  const norm = (x: string | null | undefined) => (x || '').replace(/[\s\p{P}]/gu, '').toLowerCase();
  const x = norm(a);
  const y = norm(b);
  return !!x && !!y && (x === y || x.includes(y) || y.includes(x));
}

/** 纯数字的原始热度（抖音给 11504896）统一成「1150.5万」，和豆瓣等平台的写法对齐 */
function hotText(raw: string): string {
  if (!/^\d+$/.test(raw)) return raw;
  const n = Number(raw);
  if (n >= 1e8) return `${(n / 1e8).toFixed(1)}亿`;
  if (n >= 1e4) return `${(n / 1e4).toFixed(1)}万`;
  return raw;
}
