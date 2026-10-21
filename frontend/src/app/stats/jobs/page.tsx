'use client';

/**
 * 后台任务（采集 / 调度 / 分析这些定时任务的运行统计）。调色台样式，挂在任务分区下。
 * 读数：运行数、成功率、平均耗时、失败；状态分布用 DistBars；各任务一张表（点行筛选）；最近失败列表。
 */

import React, { useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { Button, Card, CwPage, Segmented, TopBar } from '@/design/components';
import { DistBars, EmptyInstrument, Readout, Readouts, ScanSkeleton, StatusLamp, type LampTone } from '@/design/instrument';
import { TasksNav } from '@/design/TasksNav';
import { useFetch } from '@/hooks/useFetch';
import { statsJobsApi, type JobStatsResponse } from '@/lib/api';
import { timeAgoShort } from '@/lib/datetime';

const DAYS = [
  { value: '1', label: '今日' },
  { value: '7', label: '7 天' },
  { value: '30', label: '30 天' },
  { value: '90', label: '90 天' },
];

const STATUS_LABEL: Record<string, string> = { SUCCESS: '成功', FAILED: '失败', TIMEOUT: '超时', SKIPPED: '跳过', RUNNING: '运行中' };
const STATUS_COLOR: Record<string, string> = {
  SUCCESS: 'var(--cw-gr)',
  FAILED: 'var(--cw-rd)',
  TIMEOUT: 'var(--cw-yl)',
  SKIPPED: 'var(--cw-faint)',
  RUNNING: 'var(--cw-cy)',
};
const STATUS_LAMP: Record<string, LampTone> = { SUCCESS: 'ok', FAILED: 'bad', TIMEOUT: 'warn', SKIPPED: 'off', RUNNING: 'run' };

function dur(ms: number | null | undefined): string {
  if (ms == null || ms <= 0) return '—';
  if (ms < 1000) return `${ms} ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1)} s`;
  const m = s / 60;
  return m < 60 ? `${m.toFixed(1)} 分` : `${(m / 60).toFixed(1)} 时`;
}

const pct = (r: number) => `${(r * 100).toFixed(1)}%`;

export default function JobStatsPage() {
  const [days, setDays] = useState('7');
  const [jobKey, setJobKey] = useState<string | null>(null);
  const { data, loading, error, refetch } = useFetch<JobStatsResponse>(() => statsJobsApi.get(Number(days), jobKey ?? undefined), [days, jobKey], {
    initialLoading: false,
  });
  const t = data?.totals;
  const failed = t ? t.failed_count + t.timeout_count : 0;

  return (
    <CwPage>
      <TopBar title="后台任务" sub="采集、调度和分析这些定时任务跑得怎么样">
        <TasksNav />
      </TopBar>
      <div className="cw-filters">
        <Segmented label="时间范围" value={days} onChange={setDays} options={DAYS} />
        {jobKey ? (
          <Button variant="ghost" onClick={() => setJobKey(null)}>
            清除筛选：{jobKey}
          </Button>
        ) : null}
        <span className="cw-grow" />
        <Button variant="ghost" icon={<RefreshCw size={14} />} onClick={() => void refetch()} disabled={loading}>
          刷新
        </Button>
      </div>

      {error ? <EmptyInstrument kind="unplugged" title="读不到后台任务统计" reason={error} actions={<Button onClick={() => void refetch()}>重试</Button>} /> : null}
      {!data && !error ? <ScanSkeleton height={240} label="读取后台任务" /> : null}

      {data && t ? (
        t.total_runs === 0 ? (
          <EmptyInstrument kind="flat" title="这段时间没有后台任务运行" reason="定时采集、热榜快照和分析任务跑过之后会出现在这里。换一个更长的时间范围看看。" />
        ) : (
          <div className="cw-models">
            <Readouts>
              <Readout label="运行" value={t.total_runs.toLocaleString('zh-CN')} sub={`近 ${data.period.days} 天`} />
              <Readout label="成功率" value={pct(t.success_rate)} sub={`${t.success_count} 成功`} />
              <Readout label="平均耗时" value={dur(t.avg_duration_ms)} sub={`最长 ${dur(t.max_duration_ms)}`} />
              <Readout label="失败 / 超时" value={String(failed)} sub={failed ? '看下方最近失败' : '没有失败'} />
            </Readouts>

            <Card title="状态分布">
              <DistBars
                rows={data.by_status.map((r) => ({ key: r.status, label: STATUS_LABEL[r.status] || r.status, value: r.count, color: STATUS_COLOR[r.status] }))}
              />
            </Card>

            <Card title="各任务" extra={<small className="cw-muted">点一行只看这个任务</small>}>
              <table className="cw-table">
                <thead>
                  <tr>
                    <th>任务</th>
                    <th>运行</th>
                    <th>成功率</th>
                    <th>平均耗时</th>
                    <th>最近</th>
                  </tr>
                </thead>
                <tbody>
                  {data.by_job_key.map((r) => (
                    <tr key={r.job_key} onClick={() => setJobKey(jobKey === r.job_key ? null : r.job_key)} style={{ cursor: 'pointer' }} aria-selected={jobKey === r.job_key}>
                      <td className="cw-num">{r.job_key}</td>
                      <td className="cw-num">{r.runs}</td>
                      <td className="cw-num" style={r.success_rate < 0.8 ? { color: 'var(--cw-rd)' } : undefined}>{pct(r.success_rate)}</td>
                      <td className="cw-num">{dur(r.avg_duration_ms)}</td>
                      <td>
                        {r.last_status && r.last_status !== 'SUCCESS' ? <StatusLamp tone={STATUS_LAMP[r.last_status] || 'off'} label={STATUS_LABEL[r.last_status] || r.last_status} /> : null}
                        <span className="cw-muted"> {timeAgoShort(r.last_run_at)}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>

            <Card title="最近失败 / 超时" extra={<small className="cw-muted">最多 10 条</small>}>
              {data.recent_failures.length ? (
                <ol className="cw-model-rows">
                  {data.recent_failures.map((r, i) => (
                    <li key={`${r.job_key}-${r.started_at}-${i}`} className="cw-job-fail">
                      <div>
                        <StatusLamp tone={STATUS_LAMP[r.status] || 'bad'} label={STATUS_LABEL[r.status] || r.status} />
                        <b className="cw-num">{r.job_key}</b>
                        <span className="cw-muted cw-num">{timeAgoShort(r.started_at)} · {dur(r.duration_ms)}</span>
                      </div>
                      {r.error_message ? <pre>{r.error_message}</pre> : null}
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="cw-muted">这段时间没有失败。</p>
              )}
            </Card>
          </div>
        )
      ) : null}
    </CwPage>
  );
}
