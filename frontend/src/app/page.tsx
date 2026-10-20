'use client';

/**
 * 今日（改造方案 5.1）：统一信息流 + 今天的信号时间线 + 右侧栏（追踪词、跨平台共振、采集状态）。
 * 视图：全部（默认）、精选（结论为「值得做」，保留 7 天）。超过 2 天没打开时提示「你离开了 N 天」。
 */

import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useCallback, useEffect, useMemo, useState, type CSSProperties } from 'react';
import { Button, Card, CwPage, Segmented, StatusDot, TopBar } from '@/design/components';
import { DotMatrix, FeedItem, ItemDrawer, PlatformBars, ResonanceTable, SignalTimeline, platformName } from '@/design/discover';
import { mediaColor } from '@/design/tokens';
import { discoverApi, type TodayFeed, type TodaySide, type TodaySignals } from '@/lib/api/_discover';
import { MEDIA_FILTERS, SIGNAL_RANGES, type SignalRange } from '@/lib/discover';
import { Onboarding } from '@/design/onboarding';
import { OPEN_EVENT } from '@/design/command';
import { Search } from 'lucide-react';

const LEGEND: { key: keyof typeof mediaColor; label: string }[] = [
  { key: 'article', label: '文章' },
  { key: 'video', label: '视频' },
  { key: 'image', label: '图文' },
  { key: 'prompt', label: '提示词' },
  { key: 'repo', label: '仓库' },
  { key: 'list', label: '榜单' },
];

function errText(err: unknown): string {
  return err instanceof Error ? err.message : '请求失败';
}

function todayLabel(): string {
  return new Date().toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', weekday: 'short' });
}

function TodayPage() {
  const router = useRouter();
  const params = useSearchParams();
  const view = (params.get('view') === 'picks' ? 'picks' : 'all') as 'all' | 'picks';
  const [media, setMedia] = useState('');
  const [feed, setFeed] = useState<TodayFeed | null>(null);
  const [signals, setSignals] = useState<TodaySignals | null>(null);
  const [range, setRange] = useState<SignalRange>('today');
  const [side, setSide] = useState<TodaySide | null>(null);
  const [away, setAway] = useState<{ days: number; start: string; end: string } | null>(null);
  const [openId, setOpenId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [more, setMore] = useState(false);

  const loadFeed = useCallback(async () => {
    try {
      setError(null);
      setFeed(await discoverApi.feed({ view, media: media || undefined, limit: 40 }));
    } catch (err) {
      setError(errText(err));
    }
  }, [view, media]);

  useEffect(() => {
    void loadFeed();
  }, [loadFeed]);

  useEffect(() => {
    discoverApi.side().then(setSide).catch(() => setSide(null));
    discoverApi
      .seen()
      .then((s) => (s.away_days && s.gap_start && s.gap_end ? setAway({ days: s.away_days, start: s.gap_start, end: s.gap_end }) : null))
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    setSignals(null);
    discoverApi
      .signals(range)
      .then(setSignals)
      .catch(() => setSignals({ start: '', end: '', now: '', tracks: [] })); // 失败时显示空轨道，不画播放头
  }, [range]);

  const loadMore = async () => {
    if (!feed) return;
    setMore(true);
    try {
      const next = await discoverApi.feed({ view, media: media || undefined, limit: 40, offset: feed.items.length });
      setFeed({ ...feed, items: [...feed.items, ...next.items], days: next.days ? [...(feed.days || []), ...next.days] : feed.days });
    } catch (err) {
      setError(errText(err));
    } finally {
      setMore(false);
    }
  };

  const setView = (v: 'all' | 'picks') => router.replace(v === 'picks' ? '/?view=picks' : '/');

  const healthy = side?.collection;
  const term = side?.watch_terms[0];

  const legend = useMemo(
    () => (
      <div className="cw-legend">
        {LEGEND.map((l) => (
          <span key={l.key} style={{ '--c': mediaColor[l.key] } as CSSProperties}>
            <b />
            {l.label}
          </span>
        ))}
      </div>
    ),
    [],
  );

  return (
    <CwPage>
      <TopBar title="今日" sub={todayLabel()}>
        {healthy ? (
          <span className="cw-health">
            <StatusDot tone={healthy.paused ? 'warn' : 'ok'} />
            {healthy.paused ? '采集已暂停' : `今日新增 ${healthy.today_new.value ?? 0} 条`}
            {healthy.missed.value ? ` · 漏采 ${healthy.missed.value}` : ''}
          </span>
        ) : null}
        <button type="button" className="cw-search" onClick={() => window.dispatchEvent(new Event(OPEN_EVENT))}>
          <Search size={15} aria-hidden />
          <span>搜索选题、收藏、项目</span>
          <kbd>Ctrl K</kbd>
        </button>
      </TopBar>

      <Onboarding />

      {away ? (
        <div className="cw-away" role="status">
          <span>
            你离开了 <b className="cw-num">{away.days}</b> 天（{away.start} 至 {away.end}）。
          </span>
          <span className="cw-grow" />
          <Link className="cw-btn" data-variant="primary" href={`/reports?gap=${away.start}`}>
            看空档回看
          </Link>
          <Button variant="ghost" onClick={() => setAway(null)}>
            知道了
          </Button>
        </div>
      ) : null}

      <SignalTimeline data={signals} selectedId={openId} onOpen={setOpenId} legend={legend} range={range} onRange={setRange} />

      <div className="cw-today">
        <section>
          <div className="cw-feed-head">
            <h2>信号流</h2>
            <Segmented
              label="视图"
              value={view}
              onChange={setView}
              options={[
                { value: 'all', label: '全部' },
                { value: 'picks', label: '精选' },
              ]}
            />
            <Segmented label="形态" value={media} onChange={setMedia} options={MEDIA_FILTERS} />
            <span className="cw-grow" />
            <span className="cw-muted">{feed ? `${feed.total} 条` : ''}</span>
          </div>
          {error ? <div className="cw-error">{error}</div> : null}
          {!feed ? (
            <div className="cw-empty">加载中…</div>
          ) : feed.items.length === 0 ? (
            <div className="cw-empty">{view === 'picks' ? '近 7 天还没有「值得做」的内容' : '今天还没有采到内容'}</div>
          ) : view === 'picks' && feed.days ? (
            feed.days.map((d) => (
              <div key={d.date}>
                <div className="cw-feed-day cw-num">{d.date}</div>
                <ul className="cw-feed">
                  {d.items.map((item) => (
                    <FeedItem key={item.id} item={item} selected={item.id === openId} onOpen={setOpenId} />
                  ))}
                </ul>
              </div>
            ))
          ) : (
            <ul className="cw-feed">
              {feed.items.map((item) => (
                <FeedItem key={item.id} item={item} selected={item.id === openId} onOpen={setOpenId} />
              ))}
            </ul>
          )}
          {feed && feed.items.length < feed.total ? (
            <div style={{ textAlign: 'center', marginTop: 14 }}>
              <Button onClick={loadMore} disabled={more}>
                {more ? '加载中…' : '更多'}
              </Button>
            </div>
          ) : null}
        </section>

        <aside className="cw-today-side">
          <Card title="追踪词" extra={<small className="cw-muted">近 24 小时</small>}>
            {!side ? (
              <div className="cw-muted">加载中…</div>
            ) : side.watch_terms.length === 0 ? (
              <div className="cw-muted">
                还没有追踪词。<Link href="/hot?tab=terms">添加追踪词</Link>
              </div>
            ) : (
              <>
                {term ? (
                  <div className="cw-watch-block">
                    <h3 className="cw-watch-term">{term.term}</h3>
                    <div className="cw-watch-sub">
                      {Object.keys(term.per_platform).length} 个平台共 <b className="cw-num">{term.total}</b> 条
                    </div>
                    <DotMatrix dots={term.dots} label={`${term.term} 近 24 小时逐小时点阵`} />
                    <PlatformBars dist={term.per_platform} />
                  </div>
                ) : null}
                {side.watch_terms.length > 1 ? (
                  <div className="cw-watch-block cw-chips">
                    {side.watch_terms.slice(1).map((t) => (
                      <Link key={t.source_id} className="cw-chip" href={`/hot?tab=terms#term-${t.source_id}`}>
                        {t.term} <span className="cw-num">{t.total}</span>
                      </Link>
                    ))}
                    <Link className="cw-chip" href="/hot?tab=terms">
                      添加追踪词
                    </Link>
                  </div>
                ) : null}
              </>
            )}
          </Card>
          <Card title="跨平台共振" extra={<small className="cw-muted">近 48 小时</small>}>
            {side ? <ResonanceTable data={side.resonance} onOpen={setOpenId} /> : <div className="cw-muted">加载中…</div>}
          </Card>
          <Card title="采集" extra={<Link href="/sources" className="cw-muted">查看信源</Link>}>
            {healthy ? (
              <div className="cw-mini-kpis">
                <div>
                  今日新增 <b className="cw-num">{healthy.today_new.value ?? '—'}</b>
                </div>
                <div>
                  7 天成功率 <b className="cw-num">{healthy.success_rate_7d.value === null ? '—' : `${Math.round(healthy.success_rate_7d.value)}%`}</b>
                </div>
                <div>
                  待分析 <b className="cw-num">{healthy.pending_analysis.value ?? '—'}</b>
                </div>
                <div>
                  漏采 <b className="cw-num">{healthy.missed.value ?? '—'}</b>
                </div>
              </div>
            ) : (
              <div className="cw-muted">加载中…</div>
            )}
          </Card>
          {signals && signals.tracks.length ? (
            <div className="cw-muted" style={{ fontSize: 12 }}>
              {SIGNAL_RANGES.find((r) => r.value === range)?.label} {signals.tracks.map((t) => `${platformName(t.platform)} ${t.items.length}`).join(' · ')}
            </div>
          ) : null}
        </aside>
      </div>

      <ItemDrawer id={openId} onClose={() => setOpenId(null)} onChanged={() => void loadFeed()} />
    </CwPage>
  );
}

export default function Page() {
  return (
    <Suspense fallback={null}>
      <TodayPage />
    </Suspense>
  );
}
