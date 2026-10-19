'use client';

/**
 * 热点（改造方案 5.2）：热榜 / 共振 / 升温 / 追踪词。
 * 原趋势雷达（/trending）的热榜与共振、原趋势追踪（/trends）与母题配置（/my-topics/config）合并到这里。
 */

import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { InputNumber, Select, Switch, message } from 'antd';
import { Plus, RefreshCw, Star } from 'lucide-react';
import { Suspense, useCallback, useEffect, useMemo, useState, type CSSProperties } from 'react';
import { Button, Card, CwPage, Segmented, TopBar } from '@/design/components';
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

type Tab = 'list' | 'resonance' | 'rising' | 'terms';
const TABS: { id: Tab; label: string }[] = [
  { id: 'list', label: '热榜' },
  { id: 'resonance', label: '共振' },
  { id: 'rising', label: '升温' },
  { id: 'terms', label: '追踪词' },
];

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
  const label = (src: string) => sources.find((s) => s.source === src)?.display_name || src;
  const synced = (src: string) => sources.find((s) => s.source === src)?.last_synced;

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
          options={[{ value: '', label: '全部' }, ...categories.map((c) => ({ value: c, label: c }))]}
        />
        <span className="cw-grow" />
        <Button icon={<RefreshCw size={15} />} onClick={syncAll} disabled={syncing}>
          {syncing ? '同步中…' : '手动同步'}
        </Button>
      </div>
      {!items ? (
        <div className="cw-empty">加载中…</div>
      ) : bySource.size === 0 ? (
        <div className="cw-empty">还没有热榜数据，点「手动同步」抓一次</div>
      ) : (
        <div className="cw-hotlist">
          {Array.from(bySource.entries()).map(([src, rows]) => (
            <Card key={src} title={label(src)} extra={<small className="cw-num">{relativeTime(synced(src))}</small>}>
              <ol>
                {rows.slice(0, 15).map((r) => (
                  <li key={r.id}>
                    <span className="cw-rank cw-num">{r.rank}</span>
                    <a href={r.url} target="_blank" rel="noreferrer" title={r.title}>
                      {r.title}
                    </a>
                    <span className="cw-num cw-muted">{r.hot_value_raw || ''}</span>
                  </li>
                ))}
              </ol>
            </Card>
          ))}
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
        <span className="cw-muted">最低平台数</span>
        <InputNumber min={2} max={8} value={min} onChange={(v) => setMin(Number(v) || 2)} size="small" />
        <span className="cw-muted">同一事件在多个平台同时上榜</span>
      </div>
      {!clusters ? (
        <div className="cw-empty">加载中…</div>
      ) : clusters.length === 0 ? (
        <div className="cw-empty">现在没有 {min} 个平台以上同时上榜的话题</div>
      ) : (
        <ul className="cw-rows">
          {clusters.map((c) => (
            <li key={c.topic} className="cw-rise" style={{ gridTemplateColumns: 'minmax(0,1.6fr) 90px minmax(0,2fr)' }}>
              <div className="cw-rise-title">
                <b>{c.topic}</b>
                <small>{c.keywords.slice(0, 5).join(' · ')}</small>
              </div>
              <div>
                <b className="cw-num" style={{ fontSize: 18 }}>{c.resonance}</b> <span className="cw-muted">平台</span>
              </div>
              <div className="cw-rise-plats">
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
      const d = await discoverApi.follow({ event_id: eventId ?? undefined, watch_source_id: watchId ?? undefined });
      message.success('已关注，进入专题');
      router.push(`/dossiers/${d.id}`);
    } catch (err) {
      message.error(errText(err));
    }
  };

  return (
    <>
      <div className="cw-filters">
        <Segmented
          label="状态"
          value={status}
          onChange={setStatus}
          options={STATUS_FILTERS.map((f) => ({
            value: f.value,
            label: f.value && board?.status_counts[f.value] ? `${f.label} ${board.status_counts[f.value]}` : f.label,
          }))}
        />
        <span className="cw-grow" />
        <span className="cw-muted">{board?.computed_at ? `每小时计算 · ${relativeTime(board.computed_at)}` : ''}</span>
      </div>
      {!board ? (
        <div className="cw-empty">加载中…</div>
      ) : board.items.length === 0 ? (
        <div className="cw-empty">还没有话题信号。事件归并和追踪词采到内容后，每小时计算一次</div>
      ) : (
        <ul className="cw-rows">
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
                {t.representative ? (
                  <button type="button" className="cw-link-btn" onClick={() => onOpen(t.representative!.id)} title={t.representative.title}>
                    {t.representative.title}
                  </button>
                ) : null}
              </div>
              <div style={{ display: 'flex', gap: 6, alignItems: 'center', justifyContent: 'flex-end' }}>
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
    collectionApi.platforms().then((r) => setPlatforms(r.items)).catch(() => undefined);
    motherTopicsApi.list(false, 'all').then(setPresets).catch(() => setPresets([]));
  }, [load]);

  const existing = new Set((items || []).map((t) => t.term));
  const presetWords = Array.from(new Set(presets.flatMap((p) => p.keywords))).filter((k) => !existing.has(k)).slice(0, 24);

  const addPreset = async (word: string) => {
    try {
      const rec = await collectionApi.recognize(word);
      await collectionApi.createSource({ ...rec, kind: 'keyword', query: word, name: word, sync_now: false });
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
        <Button variant="primary" icon={<Plus size={15} />} onClick={() => setAdding(true)}>
          新建追踪词
        </Button>
        <span className="cw-muted">按平台拆开</span>
        <Switch size="small" checked={split} onChange={setSplit} />
      </div>
      {!items ? (
        <div className="cw-empty">加载中…</div>
      ) : items.length === 0 ? (
        <div className="cw-empty">还没有追踪词</div>
      ) : (
        <ul className="cw-rows">
          {items.map((t) => (
            <li key={t.source_id} id={`term-${t.source_id}`} className="cw-rise" style={{ gridTemplateColumns: 'minmax(0,1.2fr) 220px 76px minmax(0,1fr) 210px' }}>
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
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, justifyContent: 'flex-end' }}>
                <Select
                  size="small"
                  value={t.interval_minutes}
                  style={{ width: 104 }}
                  onChange={(v) => update(t.source_id, { interval_minutes: v })}
                  options={INTERVAL_OPTIONS.map((m) => ({ value: m, label: intervalLabel(m) }))}
                />
                <Switch size="small" checked={t.enabled} onChange={(v) => update(t.source_id, { enabled: v })} />
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
  const tab = (TABS.find((t) => t.id === params.get('tab'))?.id || 'rising') as Tab;
  const [openId, setOpenId] = useState<number | null>(null);

  return (
    <CwPage>
      <TopBar title="热点" />
      <nav className="cw-tabs" role="tablist" aria-label="热点分页">
        {TABS.map((t) => (
          <button key={t.id} type="button" role="tab" aria-selected={t.id === tab} onClick={() => router.replace(`/hot?tab=${t.id}`)}>
            {t.label}
          </button>
        ))}
      </nav>
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
