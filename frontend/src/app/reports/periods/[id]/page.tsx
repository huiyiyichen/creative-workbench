'use client';

/**
 * 空档回看 / 时间段报告（5.4）：本期大事、升温 / 降温话题、追踪词变化、错过的「值得做」、关注话题的后续、
 * 每天的条目数、一行采集概况；标注生成时的数据完整度，可重新生成（旧版本保留）。
 */

import { ScanSkeleton } from '@/design/instrument';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { message } from 'antd';
import { ArrowLeft, RefreshCw } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { Button, Card, CwPage, MiniBars, TopBar } from '@/design/components';
import { ItemDrawer, StatusTag, VerdictMark, platformName } from '@/design/discover';
import { color } from '@/design/tokens';
import { discoverApi, type PeriodDetail } from '@/lib/api/_discover';
import { topPlatforms } from '@/lib/discover';

export default function PeriodReportPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = Number(params.id);
  const [data, setData] = useState<PeriodDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [openId, setOpenId] = useState<number | null>(null);

  const load = useCallback(() => {
    discoverApi.period(id).then(setData).catch((err) => setError(err instanceof Error ? err.message : '请求失败'));
  }, [id]);
  useEffect(() => {
    load();
  }, [load]);

  const regenerate = async () => {
    setBusy(true);
    try {
      const r = await discoverApi.regeneratePeriod(id);
      message.success(`已生成 v${r.version}，旧版本保留`);
      router.push(`/reports/periods/${r.id}`);
    } catch (err) {
      message.error(err instanceof Error ? err.message : '请求失败');
    } finally {
      setBusy(false);
    }
  };

  if (error) return <CwPage><div className="cw-error">{error}</div></CwPage>;
  if (!data) return <CwPage><ScanSkeleton height={160} /></CwPage>;
  const s = data.sections;
  const c = data.completeness;

  return (
    <CwPage>
      <Link href="/reports?tab=periods" className="cw-btn" data-variant="ghost">
        <ArrowLeft size={15} />
        报告
      </Link>
      <TopBar title={data.title} sub={`v${data.version} · ${new Date(data.generated_at).toLocaleString('zh-CN', { hour12: false })}`}>
        {data.versions.length > 1 ? (
          <span className="cw-chips">
            {data.versions.map((v) => (
              <Link key={v.id} href={`/reports/periods/${v.id}`} className="cw-chip" aria-current={v.id === id ? 'page' : undefined}>
                v{v.version}
              </Link>
            ))}
          </span>
        ) : null}
        <Button icon={<RefreshCw size={15} />} onClick={regenerate} disabled={busy}>
          {busy ? '生成中…' : '数据补齐后重新生成'}
        </Button>
      </TopBar>

      {c ? (
        <div className="cw-notice">
          数据完整度：待分析 <b className="cw-num">{c.pending_analysis}</b> 条
          {c.uncollected_days.length ? ` · 未采集 ${c.uncollected_days.length} 天` : ''}
          {c.trending_missing_days.length ? ` · 热榜缺失 ${c.trending_missing_days.length} 天` : ''}
          {c.failed_sources.length ? ` · 失败的信源：${c.failed_sources.join('、')}` : ''}
          。本报告不调用模型，按条目和话题信号整理。
        </div>
      ) : null}
      {data.status === 'ERROR' ? <div className="cw-error">{data.error}</div> : null}

      {s ? (
        <div className="cw-today" style={{ marginTop: 16 }}>
          <section>
            <p style={{ margin: '0 0 6px' }}>
              {s.overview.days} 天里有 <b className="cw-num">{s.overview.collected_days}</b> 天在采集，归属到这段时间的内容{' '}
              <b className="cw-num">{s.overview.items}</b> 条。
            </p>
            <MiniBars values={s.daily_items.map((d) => d.items)} color={color.cy} label="每天的条目数" />

            <div className="cw-report-sec">
              <h3>本期大事</h3>
              {s.big_events.length ? (
                <ul className="cw-report-list">
                  {s.big_events.map((e) => (
                    <li key={e.event_id}>
                      {e.content_id ? (
                        <button type="button" className="cw-link-btn" onClick={() => setOpenId(e.content_id!)}>
                          {e.title}
                        </button>
                      ) : (
                        e.title
                      )}
                      <span className="cw-muted cw-num">
                        {e.platforms} 个平台 · {e.items} 条
                      </span>
                      <VerdictMark verdict={e.verdict} size="small" />
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="cw-muted">没有跨来源的事件</div>
              )}
            </div>

            <div className="cw-report-sec">
              <h3>升温过的话题</h3>
              {s.rising_topics.length ? (
                <ul className="cw-report-list">
                  {s.rising_topics.map((t, i) => (
                    <li key={i}>
                      <span>{t.title}</span>
                      <StatusTag status={t.status} />
                      <span className="cw-muted">
                        {topPlatforms(t.platforms, 3)
                          .map(([p, n]) => `${platformName(p)} ${n}`)
                          .join(' · ')}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="cw-muted">这段时间没有话题观测（热榜或采集缺失时为空）</div>
              )}
              {s.cooling_topics.length ? (
                <p className="cw-muted" style={{ fontSize: 13 }}>降温：{s.cooling_topics.map((t) => t.title).join('、')}</p>
              ) : null}
            </div>

            <div className="cw-report-sec">
              <h3>错过的「值得做」</h3>
              {s.missed_worth.length ? (
                <ul className="cw-report-list">
                  {s.missed_worth.map((m) => (
                    <li key={m.content_id}>
                      <button type="button" className="cw-link-btn" onClick={() => setOpenId(m.content_id)}>
                        {m.title}
                      </button>
                      <span className="cw-muted">{m.key_points.join(' · ') || m.reason}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="cw-muted">没有</div>
              )}
            </div>
          </section>
          <aside className="cw-today-side">
            <Card title="追踪词变化" extra={<small className="cw-muted">与前一段同样长度比</small>}>
              {s.watch_terms.length ? (
                <ul className="cw-report-list">
                  {s.watch_terms.map((w) => (
                    <li key={w.source_id}>
                      <span>{w.term}</span>
                      <span className="cw-grow" />
                      <b className="cw-num">{w.count}</b>
                      <span className={`cw-num ${w.delta > 0 ? 'cw-up' : 'cw-muted'}`}>
                        {w.delta > 0 ? '+' : ''}
                        {w.delta}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="cw-muted">没有追踪词</div>
              )}
            </Card>
            <Card title="你关注 / 收藏的话题有什么后续">
              {s.followed_updates.length ? (
                <ul className="cw-report-list">
                  {s.followed_updates.map((f) => (
                    <li key={f.event_id}>
                      <span>{f.title}</span>
                      <span className="cw-muted cw-num">新增 {f.new_items} 条</span>
                      <button type="button" className="cw-link-btn" onClick={() => setOpenId(f.latest.content_id)}>
                        最新：{f.latest.title}
                      </button>
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="cw-muted">没有后续</div>
              )}
            </Card>
            {c && c.trending_missing_days.length ? (
              <Card title="热榜缺失">
                <div className="cw-muted cw-num" style={{ fontSize: 12 }}>
                  {c.trending_missing_days.join('、')}
                </div>
              </Card>
            ) : null}
          </aside>
        </div>
      ) : null}
      <ItemDrawer id={openId} onClose={() => setOpenId(null)} />
    </CwPage>
  );
}
