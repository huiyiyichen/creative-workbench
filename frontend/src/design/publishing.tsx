'use client';

/** 发布：排期控件、发布后数据、发布日历（周）、效果汇总。 */

import Link from 'next/link';
import { ChevronLeft, ChevronRight, RefreshCw } from 'lucide-react';
import { useCallback, useEffect, useState, type CSSProperties } from 'react';
import { Button, Card, Sparkline } from './components';
import { toast } from './feedback';
import { kindColor } from './signal-art';
import { METRIC_LABEL, PUBLISH_PLATFORMS, publishingApi, type CalendarItem, type MetricState, type Performance, type PublishCalendar, type PublishSchedule } from '@/lib/api/_publishing';
import { bucketByDay, compactNum, fromLocalInput, toLocalInput, weekDays } from '@/lib/publishing';
import { cnParts, fmtHM } from '@/lib/time-cn';

const WD = ['一', '二', '三', '四', '五', '六', '日'];
const HEADLINE = ['views', 'likes', 'comments', 'favorites', 'shares'];

/** 产出物页：排期（未发布时）或发布后数据（已发布时）。 */
export function PublishPanel({
  outputId,
  published,
  settings,
}: {
  outputId: number;
  published: boolean;
  settings: Record<string, unknown>;
}) {
  const initial = (settings.schedule as PublishSchedule | undefined) ?? null;
  const [schedule, setSchedule] = useState<PublishSchedule | null>(initial);
  const [at, setAt] = useState(toLocalInput(initial?.at));
  const [platform, setPlatform] = useState(initial?.platform || '');
  const [note, setNote] = useState(initial?.note || '');
  const [metrics, setMetrics] = useState<MetricState>((settings.metrics as MetricState | undefined) ?? {});
  const [series, setSeries] = useState<Record<string, { at: string; value: number }[]>>({});
  const [busy, setBusy] = useState(false);

  const loadSeries = useCallback(() => {
    if (!published) return;
    publishingApi
      .metrics(outputId)
      .then((r) => setSeries(r.series))
      .catch(() => setSeries({}));
  }, [outputId, published]);
  useEffect(loadSeries, [loadSeries]);

  if (published) {
    const latest = metrics.latest || {};
    const keys = HEADLINE.filter((k) => k in latest).concat(Object.keys(latest).filter((k) => !HEADLINE.includes(k)));
    return (
      <section className="cw-publish" aria-label="发布后数据">
        <header>
          <h3>发布后数据</h3>
          <small className="cw-muted">
            {metrics.checked_at ? `${fmtHM(metrics.checked_at)} 回抓` : '还没回抓过'} · 越新抓得越勤，90 天后停止
          </small>
          <span className="cw-grow" />
          <Button
            icon={<RefreshCw size={14} />}
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                const r = await publishingApi.refreshMetrics(outputId);
                setMetrics(r.metrics);
                loadSeries();
              } catch (err) {
                toast.error(err, '回抓失败');
              } finally {
                setBusy(false);
              }
            }}
          >
            {busy ? '回抓中…' : '现在回抓'}
          </Button>
        </header>
        {keys.length ? (
          <div className="cw-publish-metrics">
            {keys.map((k) => (
              <div key={k} className="cw-readout">
                <span>{METRIC_LABEL[k] || k}</span>
                <b className="cw-num">{compactNum(latest[k])}</b>
                <Sparkline values={(series[k] || []).map((p) => p.value)} label={`${METRIC_LABEL[k] || k}变化`} width={110} height={22} />
              </div>
            ))}
          </div>
        ) : (
          <p className="cw-muted cw-small">{metrics.error || '保存发布链接后半小时内会第一次回抓；B站、抖音、小红书、YouTube 的公开数据可以读到。'}</p>
        )}
        {metrics.error && keys.length ? <p className="cw-small" style={{ color: 'var(--cw-yl)' }}>上次回抓：{metrics.error}</p> : null}
      </section>
    );
  }

  const save = async (clear = false) => {
    setBusy(true);
    try {
      const r = await publishingApi.schedule(outputId, clear ? { at: null } : { at: fromLocalInput(at), platform: platform || null, note });
      setSchedule(r.schedule);
      if (clear) setAt('');
      toast.success(clear ? '已取消排期' : '已排期，到点会提醒你');
    } catch (err) {
      toast.error(err, '排期失败');
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="cw-publish" aria-label="发布排期">
      <header>
        <h3>排期</h3>
        <small className="cw-muted">{schedule ? `排在 ${toLocalInput(schedule.at).replace('T', ' ')}` : '定个发布时间，到点提醒你'}</small>
      </header>
      <div className="cw-row cw-publish-form">
        <input className="cw-input" type="datetime-local" value={at} onChange={(e) => setAt(e.target.value)} aria-label="发布时间（北京时间）" />
        <select className="cw-input" value={platform} onChange={(e) => setPlatform(e.target.value)} aria-label="发布平台">
          <option value="">平台（可不选）</option>
          {PUBLISH_PLATFORMS.map((p) => (
            <option key={p.value} value={p.value}>
              {p.label}
            </option>
          ))}
        </select>
        <input className="cw-input" value={note} onChange={(e) => setNote(e.target.value)} placeholder="备注" maxLength={200} aria-label="备注" style={{ flex: 1 }} />
        <Button variant="primary" disabled={busy || !at} onClick={() => save()}>
          {schedule ? '改期' : '排期'}
        </Button>
        {schedule ? (
          <Button variant="ghost" disabled={busy} onClick={() => save(true)}>
            取消
          </Button>
        ) : null}
      </div>
    </section>
  );
}

function CalendarChip({ item }: { item: CalendarItem }) {
  const published = item.status === 'published';
  const views = item.metrics?.views;
  return (
    <Link
      href={`/projects/${item.project_id}/outputs/${item.id}`}
      className="cw-cal-chip"
      data-published={published ? 'true' : undefined}
      style={{ '--c': kindColor(item.kind) } as CSSProperties}
      title={`${item.project_title} · ${item.title}`}
    >
      <span className="cw-num">{item.at ? fmtHM(item.at) : ''}</span>
      <b>{item.kind_label}</b>
      <em>{item.title}</em>
      {published ? <small className="cw-num">{views !== undefined ? `${compactNum(views)} 播放` : '已发布'}</small> : <small>待发布</small>}
    </Link>
  );
}

/** 一周的发布日历 + 还没排期的待发布作品。 */
export function PublishWeek() {
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<PublishCalendar | null>(null);
  const [now] = useState(() => Date.now());
  const days = weekDays(now, offset);
  const start = days[0];
  useEffect(() => {
    const s = new Date(start).toISOString();
    const e = new Date(start + 7 * 86400000).toISOString();
    publishingApi
      .calendar(s, e)
      .then(setData)
      .catch((err) => toast.error(err, '加载日历失败'));
  }, [start]);
  const buckets = data ? bucketByDay(data.items, days) : days.map(() => []);
  const today = days.findIndex((d) => now >= d && now < d + 86400000);
  const first = cnParts(days[0]);
  const last = cnParts(days[6]);
  return (
    <div className="cw-stack">
      <section className="cw-instrument" aria-label="发布日历">
        <div className="cw-tl-head" style={{ padding: '0 0 12px' }}>
          <h2>发布日历</h2>
          <span className="cw-num cw-muted">
            {first.mo}/{first.d} – {last.mo}/{last.d}
          </span>
          <span className="cw-grow" />
          <Button size="icon" aria-label="上一周" onClick={() => setOffset((o) => o - 1)}>
            <ChevronLeft size={15} />
          </Button>
          <Button onClick={() => setOffset(0)} disabled={offset === 0}>
            本周
          </Button>
          <Button size="icon" aria-label="下一周" onClick={() => setOffset((o) => o + 1)}>
            <ChevronRight size={15} />
          </Button>
        </div>
        <div className="cw-cal-week">
          {days.map((d, i) => {
            const p = cnParts(d);
            return (
              <div key={d} className="cw-cal-day" data-today={i === today ? 'true' : undefined} data-past={offset < 0 || (offset === 0 && i < today) ? 'true' : undefined}>
                <header>
                  <span>周{WD[i]}</span>
                  <b className="cw-num">{p.d}</b>
                </header>
                <div className="cw-cal-items">
                  {buckets[i].map((it) => (
                    <CalendarChip key={it.id} item={it} />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </section>
      {data && data.backlog.length ? (
        <Card title="做好了还没排期" extra={<small className="cw-muted">{data.backlog.length} 件</small>}>
          <ul className="cw-cal-backlog">
            {data.backlog.map((b) => (
              <li key={b.id} style={{ '--c': kindColor(b.kind) } as CSSProperties}>
                <i />
                <Link href={`/projects/${b.project_id}/outputs/${b.id}`}>{b.title}</Link>
                <span className="cw-muted">{b.kind_label}</span>
                <span className="cw-muted">{b.project_title}</span>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}
    </div>
  );
}

/** 效果：按形态 / 平台的中位数，和表现最好的几件。 */
export function PerformancePanel() {
  const [data, setData] = useState<Performance | null>(null);
  useEffect(() => {
    publishingApi
      .performance()
      .then(setData)
      .catch((err) => toast.error(err, '加载效果失败'));
  }, []);
  if (!data) return <div className="cw-instrument"><div className="cw-tl-scan" style={{ marginLeft: 0 }}><i /></div></div>;
  if (!data.tracked) {
    return (
      <section className="cw-instrument">
        <div className="cw-tl-flat" style={{ marginLeft: 0 }}>
          <svg viewBox="0 0 400 40" preserveAspectRatio="none" aria-hidden>
            <line x1="0" x2="400" y1="20" y2="20" />
            <circle r="3" cy="20" cx="0" />
          </svg>
          <span>{data.published ? `已发布 ${data.published} 件，还没回抓到数据` : '发布后把链接填回产出页，这里会按形态和平台比较效果'}</span>
        </div>
      </section>
    );
  }
  const maxKind = Math.max(1, ...data.by_kind.map((g) => g.median.views || 0));
  return (
    <div className="cw-split" style={{ marginTop: 0 }}>
      <div className="cw-stack">
        <Card title="按形态" extra={<small className="cw-muted">播放 / 阅读中位数</small>}>
          <div className="cw-distbars">
            {data.by_kind.map((g, i) => (
              <div key={g.key} style={{ '--c': kindColor(g.key), '--i': i } as CSSProperties}>
                <span>
                  {g.label} <em className="cw-num">×{g.count}</em>
                </span>
                <s style={{ width: `${Math.max(1, ((g.median.views || 0) / maxKind) * 100)}%` }} />
                <b className="cw-num">{compactNum(g.median.views)}</b>
                <em className="cw-num">{g.median.likes !== undefined ? `赞 ${compactNum(g.median.likes)}` : ''}</em>
              </div>
            ))}
          </div>
        </Card>
        <Card title="按平台">
          <table className="cw-table">
            <thead>
              <tr>
                <th>平台</th>
                <th className="cw-num-col">件数</th>
                {HEADLINE.slice(0, 3).map((k) => (
                  <th key={k} className="cw-num-col">
                    {METRIC_LABEL[k]}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.by_platform.map((g) => (
                <tr key={g.key}>
                  <td>{g.label}</td>
                  <td className="cw-num cw-num-col">{g.count}</td>
                  {HEADLINE.slice(0, 3).map((k) => (
                    <td key={k} className="cw-num cw-num-col">
                      {compactNum(g.median[k])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>
      <Card title="表现最好">
        <ol className="cw-perf-top">
          {data.top.map((t, i) => (
            <li key={t.id} style={{ '--c': kindColor(t.kind) } as CSSProperties}>
              <b className="cw-num">{i + 1}</b>
              <Link href={`/projects/${t.project_id}/outputs/${t.id}`}>{t.title}</Link>
              <small className="cw-num cw-muted">
                {t.kind_label} · {compactNum(t.metrics.views)} 播放 · {compactNum(t.metrics.likes)} 赞
              </small>
            </li>
          ))}
        </ol>
      </Card>
    </div>
  );
}
