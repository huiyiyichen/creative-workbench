'use client';

/** 花费总览：分析、报告、创作、阅读的模型花费 + 生图 / 视频 / 配乐的生成花费，按天、按用途、按模型、按项目。 */

import Link from 'next/link';
import { useEffect, useState, type CSSProperties } from 'react';
import { Card, CwPage, Segmented, TopBar } from '@/design/components';
import { toast } from '@/design/feedback';
import { EmptyInstrument, Readout, ScanSkeleton } from '@/design/instrument';
import { costsApi, type CostSummary } from '@/lib/api/_costs';
import { GROUP_ORDER, groupColor, stackDays, vsAvg, yuan } from '@/lib/costs';

const RANGES = [
  { value: '7', label: '7 天' },
  { value: '30', label: '30 天' },
  { value: '90', label: '90 天' },
];

const CH = 140; // 柱区高度

function DailyBars({ data }: { data: CostSummary }) {
  const days = stackDays(data.series, CH);
  const [hover, setHover] = useState<number | null>(null);
  const n = days.length;
  const max = Math.max(0, ...data.series.map((d) => d.total));
  const h = hover !== null ? data.series[hover] : null;
  return (
    <div className="cw-cost-chart">
      <div className="cw-cost-yaxis cw-num" aria-hidden>
        <span>{yuan(max)}</span>
        <span>{yuan(max / 2)}</span>
        <span>¥0</span>
      </div>
      <div className="cw-cost-plot" onPointerLeave={() => setHover(null)}>
        <svg viewBox={`0 0 ${n * 10} ${CH}`} preserveAspectRatio="none" role="img" aria-label={`近 ${n} 天每日花费`}>
          {[0.25, 0.5, 0.75].map((y) => (
            <line key={y} className="cw-cost-grid" x1="0" x2={n * 10} y1={CH * y} y2={CH * y} />
          ))}
          {days.map((d, i) => (
            <g
              key={d.date}
              className="cw-cost-bar"
              data-today={i === n - 1 ? 'true' : undefined}
              data-dim={hover !== null && hover !== i ? 'true' : undefined}
              style={{ '--i': Math.min(i, 40) } as CSSProperties}
              onPointerEnter={() => setHover(i)}
            >
              <rect className="cw-cost-hit" x={i * 10} y="0" width="10" height={CH} />
              {d.segs.length === 0 ? (
                <rect className="cw-cost-zero" x={i * 10 + 2} y={CH - 1.5} width="6" height="1.5" />
              ) : (
                d.segs.map((s) => <rect key={s.key} x={i * 10 + 2} y={s.y} width="6" height={Math.max(0.6, s.h)} style={{ fill: groupColor(s.key) }} />)
              )}
            </g>
          ))}
        </svg>
        <div className="cw-cost-xaxis cw-num" aria-hidden>
          <span>{data.start.slice(5).replace('-', '/')}</span>
          <span>今天</span>
        </div>
        {h ? (
          <div className="cw-cost-tip" style={{ left: `${((hover! + 0.5) / n) * 100}%` }}>
            <b className="cw-num">{h.date.slice(5).replace('-', '/')}</b>
            <span className="cw-num">{yuan(h.total)}</span>
            {GROUP_ORDER.filter((k) => typeof h[k] === 'number' && (h[k] as number) > 0).map((k) => (
              <small key={k}>
                <i style={{ background: groupColor(k) }} />
                {data.groups.find((g) => g.key === k)?.label ?? k} <em className="cw-num">{yuan(h[k] as number)}</em>
              </small>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function BudgetMeter({ budget }: { budget: CostSummary['analysis_budget'] }) {
  const ratio = budget.budget > 0 ? Math.min(1, budget.spent / budget.budget) : 0;
  const tone = ratio >= 1 ? 'rd' : ratio >= 0.8 ? 'yl' : 'gr';
  return (
    <div className="cw-readout">
      <span>今日分析预算</span>
      <b className="cw-num">
        {yuan(budget.spent)}
        <em> / {yuan(budget.budget)}</em>
      </b>
      <div className="cw-meter" data-tone={tone} role="meter" aria-valuemin={0} aria-valuemax={budget.budget} aria-valuenow={budget.spent} aria-label="今日分析预算使用">
        <i style={{ width: `${ratio * 100}%` }} />
      </div>
    </div>
  );
}

function DistBars({ rows, total }: { rows: { key: string; label: string; cost: number; count: number; color: string }[]; total: number }) {
  const max = Math.max(0, ...rows.map((r) => r.cost));
  return (
    <div className="cw-distbars">
      {rows.map((r, i) => (
        <div key={r.key} style={{ '--c': r.color, '--i': i } as CSSProperties}>
          <span>{r.label}</span>
          <s style={{ width: `${max > 0 ? Math.max(1, (r.cost / max) * 100) : 0}%` }} />
          <b className="cw-num">{yuan(r.cost)}</b>
          <em className="cw-num">{total > 0 ? `${Math.round((r.cost / total) * 100)}%` : ''}</em>
        </div>
      ))}
    </div>
  );
}

export default function CostsPage() {
  const [days, setDays] = useState('30');
  const [data, setData] = useState<CostSummary | null>(null);
  useEffect(() => {
    costsApi
      .summary(Number(days))
      .then(setData)
      .catch((err) => toast.error(err, '加载花费失败'));
  }, [days]);
  const delta = data ? vsAvg(data.today, data.avg_7d) : null;
  const empty = data !== null && data.total === 0;
  return (
    <CwPage>
      <TopBar title="花费" sub={data ? <span className="cw-num">{`近 ${data.days} 天 · ${yuan(data.total)}`}</span> : null}>
        <Segmented label="时间范围" value={days} onChange={setDays} options={RANGES} />
      </TopBar>

      {data && empty ? (
        <EmptyInstrument
          kind="unplugged"
          title={`近 ${data.days} 天还没有花费`}
          reason={`分析、写稿、日报、生图、视频生成的费用都会记在这里，按天、按用途、按项目分开看。今日分析预算 ${yuan(data.analysis_budget.budget)}。`}
          actions={
            <>
              <Link className="cw-btn" data-variant="primary" href="/admin/model-eval">
                配置模型
              </Link>
              <Link className="cw-link-btn" href="/settings/generation">
                配置生成服务
              </Link>
            </>
          }
        />
      ) : null}
      <section className="cw-instrument cw-cost-hero" data-hero="true" aria-label="花费读数" hidden={Boolean(data && empty)}>
        {!data ? (
          <ScanSkeleton height={220} />
        ) : (
          <>
            <div className="cw-readouts">
              <Readout label={`近 ${data.days} 天`} value={yuan(data.total)} sub={`模型 ${yuan(data.llm)} · 生成 ${yuan(data.generation)}`} />
              <Readout label="今天" value={yuan(data.today)} sub={delta ? `比 7 日均值 ${delta.text}` : '没有可比的均值'} tone={delta ? (delta.up ? 'bad' : 'good') : undefined} />
              <BudgetMeter budget={data.analysis_budget} />
              <Readout
                label="调用 / 任务"
                value={`${data.calls.toLocaleString('zh-CN')} / ${data.jobs.toLocaleString('zh-CN')}`}
                sub={data.failed ? `${data.failed} 次失败` : '没有失败'}
                tone={data.failed ? 'bad' : undefined}
              />
            </div>
            {empty ? (
              <div className="cw-tl-flat">
                <svg viewBox="0 0 400 40" preserveAspectRatio="none" aria-hidden>
                  <line x1="0" x2="400" y1="20" y2="20" />
                  <circle r="3" cy="20" cx="0" />
                </svg>
                <span>这段时间没有产生花费：配置模型、生成服务后，分析、写稿、生图的费用都会记在这里</span>
              </div>
            ) : (
              <DailyBars data={data} />
            )}
            <div className="cw-legend cw-cost-legend">
              {data.groups.map((g) => (
                <span key={g.key}>
                  <b style={{ background: groupColor(g.key) }} />
                  {g.label}
                </span>
              ))}
            </div>
          </>
        )}
      </section>

      {data && !empty ? (
        <div className="cw-split">
          <div className="cw-stack">
            <Card title="按用途">
              <DistBars rows={data.groups.map((g) => ({ ...g, color: groupColor(g.key) }))} total={data.total} />
            </Card>
            <Card title="按场景" extra={<small className="cw-muted">模型调用</small>}>
              <table className="cw-table cw-cost-table">
                <thead>
                  <tr>
                    <th>场景</th>
                    <th className="cw-num-col">次数</th>
                    <th className="cw-num-col">花费</th>
                    <th className="cw-num-col">每次</th>
                  </tr>
                </thead>
                <tbody>
                  {data.scenes.map((s) => (
                    <tr key={s.key}>
                      <td>
                        <i className="cw-swatch" style={{ background: groupColor(s.group || 'other') }} />
                        {s.label}
                      </td>
                      <td className="cw-num cw-num-col">{s.count.toLocaleString('zh-CN')}</td>
                      <td className="cw-num cw-num-col">{yuan(s.cost)}</td>
                      <td className="cw-num cw-num-col cw-muted">{s.count ? yuan(s.cost / s.count) : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          </div>
          <aside className="cw-stack">
            <Card title="模型与服务">
              <DistBars rows={data.models.map((m) => ({ ...m, color: m.label.includes(' · ') ? 'var(--cw-mg)' : 'var(--cw-cy)' }))} total={data.total} />
              {data.unpriced_jobs ? <p className="cw-muted cw-small">有 {data.unpriced_jobs} 个生成任务厂商没有回报价格，按 ¥0 计。可以在「设置 · 生成服务」里填单价。</p> : null}
            </Card>
            <Card title="项目">
              {data.projects.length === 0 ? (
                <p className="cw-muted cw-small">还没有记到具体项目上的花费。</p>
              ) : (
                <ul className="cw-cost-projects">
                  {data.projects.map((p) => (
                    <li key={p.id}>
                      <Link href={`/projects/${p.id}`}>{p.title}</Link>
                      <span className="cw-num">{yuan(p.cost)}</span>
                      <small className="cw-num cw-muted">
                        模型 {yuan(p.llm)} · 生成 {yuan(p.generation)}
                      </small>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </aside>
        </div>
      ) : null}
    </CwPage>
  );
}
