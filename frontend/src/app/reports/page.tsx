'use client';

/**
 * 报告（改造方案 5.4）：归档日历（每天的头条、未采集）、日报 / 周刊 / 月刊入口、空档回看、任意时间段、全文搜索。
 */

import { ScanSkeleton } from '@/design/instrument';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { DatePicker, message } from 'antd';
import type { Dayjs } from 'dayjs';
import { ChevronLeft, ChevronRight, FileText } from 'lucide-react';
import { Suspense, useCallback, useEffect, useMemo, useState, type CSSProperties } from 'react';
import { cnParts } from '@/lib/time-cn';
import { Button, Card, CwPage, SearchField, Segmented, TopBar } from '@/design/components';
import { discoverApi, type PeriodSummary, type ReportCalendar, type ReportHit } from '@/lib/api/_discover';
import { monthGrid } from '@/lib/discover';

type Tab = 'archive' | 'periods' | 'search';
const WEEK = ['一', '二', '三', '四', '五', '六', '日'];
const STATE_TEXT = { report: '', collected: '', uncollected: '未采集', future: '' } as const;

function errText(err: unknown): string {
  return err instanceof Error ? err.message : '请求失败';
}

function hitHref(h: ReportHit): string {
  if (h.kind === 'daily') return `/daily?date=${h.key}`;
  if (h.kind === 'weekly') return '/weekly';
  if (h.kind === 'monthly') return '/monthly';
  return `/reports/periods/${h.id}`;
}

function Archive() {
  const now = new Date();
  const [ym, setYm] = useState({ y: now.getFullYear(), m: now.getMonth() + 1 });
  const [cal, setCal] = useState<ReportCalendar | null>(null);
  const [picked, setPicked] = useState<string | null>(null);
  const [cont, setCont] = useState<{ previous_date: string | null; continued: string[]; new: string[]; dropped: string[] } | null>(null);

  useEffect(() => {
    setCal(null);
    discoverApi.calendar(ym.y, ym.m).then(setCal).catch((err) => message.error(errText(err)));
  }, [ym]);

  useEffect(() => {
    setCont(null);
    if (picked) discoverApi.continuity(picked).then(setCont).catch(() => setCont(null));
  }, [picked]);

  const byDate = useMemo(() => new Map((cal?.days || []).map((d) => [d.date, d])), [cal]);
  const gapDays = useMemo(() => {
    const set = new Set<string>();
    for (const g of cal?.gaps || []) {
      for (let d = new Date(`${g.start_date}T00:00:00`); d <= new Date(`${g.end_date}T00:00:00`); d.setDate(d.getDate() + 1)) {
        set.add(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`);
      }
    }
    return set;
  }, [cal]);
  const shift = (n: number) => setYm(({ y, m }) => {
    const d = new Date(y, m - 1 + n, 1);
    return { y: d.getFullYear(), m: d.getMonth() + 1 };
  });
  const pickedDay = picked ? byDate.get(picked) : null;
  const monthDays = cal?.days || [];
  const maxItems = Math.max(1, ...monthDays.map((d) => d.items || 0));
  const [todayKey] = useState(() => {
    const p = cnParts(Date.now());
    return `${p.y}-${String(p.mo).padStart(2, '0')}-${String(p.d).padStart(2, '0')}`;
  });

  return (
    <div className="cw-today">
      <section>
        <div className="cw-filters">
          <Button size="icon" variant="ghost" aria-label="上个月" onClick={() => shift(-1)}>
            <ChevronLeft size={16} />
          </Button>
          <b className="cw-num" style={{ fontSize: 16 }}>
            {ym.y} 年 {ym.m} 月
          </b>
          <Button size="icon" variant="ghost" aria-label="下个月" onClick={() => shift(1)}>
            <ChevronRight size={16} />
          </Button>
          <span className="cw-grow" />
          <span className="cw-legend" style={{ fontSize: 12 }}>
            <span><i className="cw-cal-lamp" /> 有日报</span>
            <span><i className="cw-cal-key" data-k="heat" /> 颜色越亮采得越多</span>
            <span><i className="cw-cal-key" data-k="none" /> 未采集</span>
            <span><i className="cw-cal-key" data-k="gap" /> 空档</span>
          </span>
        </div>
        <div className="cw-cal">
          {WEEK.map((w) => (
            <div key={w} className="cw-cal-head">
              周{w}
            </div>
          ))}
          {monthGrid(ym.y, ym.m).map((date, i) => {
            if (!date) return <div key={`e${i}`} />;
            const d = byDate.get(date);
            const state = d?.state || 'future';
            return (
              <button
                key={date}
                type="button"
                className="cw-cal-cell"
                data-state={state}
                data-gap={gapDays.has(date) ? 'true' : undefined}
                aria-pressed={picked === date}
                data-today={date === todayKey ? 'true' : undefined}
                onClick={() => setPicked(date)}
                style={{ '--h': d && d.items ? Math.max(0.12, Math.min(1, Math.log1p(d.items) / Math.log1p(maxItems))) : 0 } as CSSProperties}
              >
                <span className="cw-cal-day cw-num">
                  {Number(date.slice(8))}
                  {state === 'report' ? <i className="cw-cal-lamp" title="有日报" /> : null}
                  <small className="cw-cal-count">{d && d.items ? d.items : ''}</small>
                </span>
                <span className="cw-cal-headline">{d?.headline || STATE_TEXT[state]}</span>
                <span className="cw-cal-level" aria-hidden />
              </button>
            );
          })}
        </div>
      </section>
      <aside className="cw-today-side">
        {pickedDay ? (
          <Card title={pickedDay.date}>
            {pickedDay.report_id ? (
              <>
                <p style={{ margin: '0 0 8px' }}>{pickedDay.headline || '日报'}</p>
                <p className="cw-muted" style={{ fontSize: 12 }}>
                  {pickedDay.edition === 'final' ? '完整版' : '当天快照'} · {pickedDay.items} 条内容
                </p>
                {cont ? (
                  <div style={{ fontSize: 13, display: 'grid', gap: 4, margin: '8px 0' }}>
                    {cont.previous_date ? <span className="cw-muted">对比上期 {cont.previous_date}</span> : null}
                    {cont.continued.length ? <span>后续：{cont.continued.join('、')}</span> : null}
                    {cont.new.length ? <span>新出现：{cont.new.join('、')}</span> : null}
                    {cont.dropped.length ? <span className="cw-muted">降温：{cont.dropped.join('、')}</span> : null}
                  </div>
                ) : null}
                <Link className="cw-btn" data-variant="primary" href={`/daily?date=${pickedDay.date}`}>
                  <FileText size={15} />
                  打开日报
                </Link>
              </>
            ) : pickedDay.state === 'uncollected' ? (
              <p className="cw-muted">这天没有采集，不生成日报。</p>
            ) : pickedDay.state === 'collected' ? (
              <>
                <p className="cw-muted">有 {pickedDay.items} 条内容，还没有日报。</p>
                <Link className="cw-btn" href={`/daily?date=${pickedDay.date}`}>
                  去生成
                </Link>
              </>
            ) : (
              <p className="cw-muted">还没到这天。</p>
            )}
          </Card>
        ) : null}
        <Card title="周刊与月刊">
          <ul className="cw-report-list">
            {(cal?.weeklies || []).map((w) => (
              <li key={w.id}>
                <Link href="/weekly">周刊 {w.label}</Link>
              </li>
            ))}
            {cal?.monthly_id ? (
              <li>
                <Link href="/monthly">
                  月刊 {ym.y}-{String(ym.m).padStart(2, '0')}
                </Link>
              </li>
            ) : null}
            {cal && !cal.weeklies.length && !cal.monthly_id ? <li className="cw-muted">这个月还没有</li> : null}
          </ul>
        </Card>
        <Card title="空档回看">
          {cal?.gaps.length ? (
            <ul className="cw-report-list">
              {cal.gaps.map((g) => (
                <li key={g.id}>
                  <Link href={`/reports/periods/${g.id}`}>{g.title}</Link>
                </li>
              ))}
            </ul>
          ) : (
            <div className="cw-muted">这个月没有空档</div>
          )}
        </Card>
      </aside>
    </div>
  );
}

function Periods({ focusGap }: { focusGap: string | null }) {
  const router = useRouter();
  const [items, setItems] = useState<PeriodSummary[] | null>(null);
  const [range, setRange] = useState<[Dayjs | null, Dayjs | null] | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    discoverApi.periods().then((r) => setItems(r.items)).catch((err) => message.error(errText(err)));
  }, []);
  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!focusGap || !items) return;
    const hit = items.find((p) => p.kind === 'gap' && p.start_date === focusGap);
    if (hit) router.replace(`/reports/periods/${hit.id}`);
  }, [focusGap, items, router]);

  const create = async () => {
    if (!range?.[0] || !range?.[1]) return;
    setBusy(true);
    try {
      const r = await discoverApi.createPeriod(range[0].format('YYYY-MM-DD'), range[1].format('YYYY-MM-DD'));
      router.push(`/reports/periods/${r.id}`);
    } catch (err) {
      message.error(errText(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="cw-filters">
        <span className="cw-muted">任意时间段</span>
        <DatePicker.RangePicker value={range} onChange={(v) => setRange(v as [Dayjs | null, Dayjs | null] | null)} />
        <Button variant="primary" onClick={create} disabled={busy || !range?.[0] || !range?.[1]}>
          {busy ? '生成中…' : '生成报告'}
        </Button>
        <span className="cw-grow" />
        <span className="cw-muted" style={{ fontSize: 12 }}>
          连续 2 天以上没有采集时，开机补采完成后自动生成空档回看
        </span>
      </div>
      {!items ? (
        <ScanSkeleton shape="scan" height={160} />
      ) : items.length === 0 ? (
        <div className="cw-empty">还没有空档回看或时间段报告</div>
      ) : (
        <table className="cw-table">
          <thead>
            <tr>
              <th>报告</th>
              <th>范围</th>
              <th>版本</th>
              <th>完整度</th>
              <th>生成</th>
            </tr>
          </thead>
          <tbody>
            {items.map((p) => (
              <tr key={p.id}>
                <td>
                  <Link href={`/reports/periods/${p.id}`}>{p.title}</Link>
                </td>
                <td className="cw-num">
                  {p.start_date} – {p.end_date}
                </td>
                <td className="cw-num">v{p.version}</td>
                <td className="cw-muted" style={{ fontSize: 12 }}>
                  {p.completeness
                    ? `待分析 ${p.completeness.pending_analysis} · 未采集 ${p.completeness.uncollected_days.length} 天 · 热榜缺 ${p.completeness.trending_missing_days.length} 天`
                    : '—'}
                </td>
                <td className="cw-num">{new Date(p.generated_at).toLocaleString('zh-CN', { hour12: false })}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}

function Search() {
  const [q, setQ] = useState('');
  const [hits, setHits] = useState<ReportHit[] | null>(null);
  const run = async (value: string) => {
    if (!value.trim()) return;
    try {
      setHits((await discoverApi.searchReports(value.trim())).items);
    } catch (err) {
      message.error(errText(err));
    }
  };
  return (
    <>
      <SearchField placeholder="搜索所有日报、周刊、月刊、空档回看（回车）" width="min(480px, 100%)" value={q} onChange={setQ} onSubmit={run} />
      {hits === null ? null : hits.length === 0 ? (
        <div className="cw-empty">没有找到</div>
      ) : (
        <ul className="cw-report-list" style={{ marginTop: 14 }}>
          {hits.map((h) => (
            <li key={`${h.kind}-${h.id}`}>
              <Link href={hitHref(h)}>{h.label}</Link>
              {h.snippet ? <span className="cw-muted">{h.snippet}</span> : null}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

function ReportsPage() {
  const router = useRouter();
  const params = useSearchParams();
  const gap = params.get('gap');
  const tab = (gap ? 'periods' : (params.get('tab') as Tab)) || 'archive';
  return (
    <CwPage>
      <TopBar title="报告">
        <Segmented
          label="报告分页"
          value={tab}
          onChange={(v) => router.replace(`/reports?tab=${v}`)}
          options={[
            { value: 'archive', label: '归档' },
            { value: 'periods', label: '空档与时间段' },
            { value: 'search', label: '搜索' },
          ]}
        />
        <Link className="cw-btn" data-variant="primary" href="/daily">
          今日日报
        </Link>
      </TopBar>
      {tab === 'archive' ? <Archive /> : null}
      {tab === 'periods' ? <Periods focusGap={gap} /> : null}
      {tab === 'search' ? <Search /> : null}
    </CwPage>
  );
}

export default function Page() {
  return (
    <Suspense fallback={null}>
      <ReportsPage />
    </Suspense>
  );
}
