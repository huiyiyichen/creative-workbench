'use client';

import Link from 'next/link';
import { Select, Tooltip, message } from 'antd';
import { Pause, Play, Plus, RefreshCw, Settings2, Undo2 } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Button, Card, CwPage, MiniBars, Num, SectionHead, StatusDot, TopBar } from '@/design/components';
import { mediaColor } from '@/design/tokens';
import {
  collectionApi,
  type AutoActionItem,
  type CollectionFunnel,
  type CollectionOverview,
  type MetricPair,
  type PlatformInfo,
  type SourceHealthRow,
} from '@/lib/api/_collection';
import { AddSourceModal, BudgetLine, FunnelSettingsModal, PlatformList, RecentDrawer } from './_parts';
import { InsightsSections, SuggestionsCard } from './_insights';
import {
  ACTION_LABEL,
  ERROR_KIND_LABEL,
  HEALTH_LABEL,
  HEALTH_TONE,
  INTERVAL_OPTIONS,
  KIND_LABEL,
  PLATFORM_LABEL,
  SKIP_REASON_LABEL,
  actionTone,
  delta,
  intervalLabel,
  relativeTime,
} from '@/lib/collection';

const TABS = [
  { href: '/admin/sources', label: '信源列表' },
  { href: '/sources', label: '采集' },
  { href: '/admin/contents', label: '内容' },
];

function errorText(err: unknown): string {
  return err instanceof Error ? err.message : '请求失败';
}

function Kpi({ label, pair, digits = 0, suffix = '', higherIsBetter = true }: {
  label: string;
  pair: MetricPair | undefined;
  digits?: number;
  suffix?: string;
  higherIsBetter?: boolean;
}) {
  const d = pair ? delta(pair, higherIsBetter) : null;
  return (
    <div className="cw-kpi">
      <div className="cw-kpi-label">{label}</div>
      <div className="cw-kpi-value">
        <b>
          <Num value={pair?.value} digits={digits} suffix={suffix} />
        </b>
        {d ? (
          <span className="cw-delta" data-dir={d.dir} title="与 7 天前相比">
            {d.text}
          </span>
        ) : null}
      </div>
    </div>
  );
}

function HealthTable({
  rows,
  busy,
  onSync,
  onToggle,
  onInterval,
  onOpen,
}: {
  rows: SourceHealthRow[];
  busy: Set<number>;
  onSync: (row: SourceHealthRow) => void;
  onToggle: (row: SourceHealthRow) => void;
  onInterval: (row: SourceHealthRow, minutes: number) => void;
  onOpen: (row: SourceHealthRow) => void;
}) {
  if (!rows.length) return <div className="cw-empty">还没有信源</div>;
  return (
    <table className="cw-table">
      <thead>
        <tr>
          <th>信源</th>
          <th>状态</th>
          <th>上次成功</th>
          <th>下次计划</th>
          <th>7 天成功率</th>
          <th>最近失败</th>
          <th>每日新增</th>
          <th>间隔</th>
          <th aria-label="动作" />
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => {
          const intervalOptions = Array.from(new Set([...INTERVAL_OPTIONS, row.interval_minutes])).sort((a, b) => a - b);
          return (
            <tr key={row.id}>
              <td>
                <button type="button" className="cw-link-btn" onClick={() => onOpen(row)} title="查看最近采到">
                  <div className="cw-cell-title">{row.name}</div>
                  <div className="cw-cell-sub">
                    {[
                      row.kind ? KIND_LABEL[row.kind] : null,
                      row.kind === 'keyword' && row.platforms?.length
                        ? row.platforms.map((p) => PLATFORM_LABEL[p] ?? p).join('/')
                        : row.platform
                          ? (PLATFORM_LABEL[row.platform] ?? row.platform)
                          : null,
                      row.source_type,
                    ]
                      .filter(Boolean)
                      .join(' · ')}
                  </div>
                </button>
              </td>
              <td>
                <span className="cw-health">
                  <StatusDot tone={HEALTH_TONE[row.state]} />
                  {HEALTH_LABEL[row.state]}
                </span>
                {row.auto_pause_reason ? <div className="cw-cell-sub">{row.auto_pause_reason}</div> : null}
              </td>
              <td className="cw-num cw-dimtext">{relativeTime(row.last_success_at)}</td>
              <td className="cw-num cw-dimtext">{row.enabled ? relativeTime(row.next_run_at) : '—'}</td>
              <td>
                <Num value={row.success_rate_7d} digits={0} suffix="%" />
                <div className="cw-cell-sub cw-num">{row.runs_7d} 次</div>
              </td>
              <td>
                {row.last_error ? (
                  <Tooltip title={row.last_error.message || undefined}>
                    <span className="cw-dimtext">
                      {ERROR_KIND_LABEL[row.last_error.kind || 'other'] ?? row.last_error.kind}
                      {row.last_error.http_status ? <span className="cw-num"> {row.last_error.http_status}</span> : null}
                    </span>
                    <div className="cw-cell-sub">{relativeTime(row.last_error.at)}</div>
                  </Tooltip>
                ) : (
                  <span className="cw-muted">—</span>
                )}
              </td>
              <td>
                <MiniBars values={row.daily_new} color={mediaColor.prompt} label={`近 7 天每日新增：${row.daily_new.join('、')}`} />
              </td>
              <td>
                <Select
                  size="small"
                  variant="borderless"
                  value={row.interval_minutes}
                  onChange={(v: number) => onInterval(row, v)}
                  options={intervalOptions.map((m) => ({ value: m, label: intervalLabel(m) }))}
                  popupMatchSelectWidth={false}
                  aria-label={`${row.name} 同步间隔`}
                />
                {row.base_interval_minutes ? <div className="cw-cell-sub">限流退避中</div> : null}
              </td>
              <td>
                <span style={{ display: 'inline-flex', gap: 6 }}>
                  <Tooltip title="立即同步">
                    <Button
                      size="icon"
                      icon={<RefreshCw className={busy.has(row.id) ? 'animate-spin' : undefined} />}
                      disabled={!row.enabled || busy.has(row.id)}
                      onClick={() => onSync(row)}
                      aria-label={`立即同步 ${row.name}`}
                    />
                  </Tooltip>
                  <Tooltip title={row.enabled ? '停用' : '启用'}>
                    <Button
                      size="icon"
                      icon={row.enabled ? <Pause /> : <Play />}
                      onClick={() => onToggle(row)}
                      aria-label={`${row.enabled ? '停用' : '启用'} ${row.name}`}
                    />
                  </Tooltip>
                </span>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function Funnel({ funnel }: { funnel: CollectionFunnel | null }) {
  if (!funnel) return <div className="cw-empty">加载中</div>;
  const max = Math.max(1, ...funnel.stages.map((s) => s.value ?? 0));
  return (
    <>
      <div className="cw-funnel">
        {funnel.stages.map((stage) => (
          <div key={stage.key} className="cw-funnel-step">
            <div className="cw-kpi-label">{stage.label}</div>
            <b>
              <Num value={stage.value} />
            </b>
            <div className="cw-funnel-bar" style={{ width: `${stage.value === null ? 0 : Math.max(4, (stage.value / max) * 100)}%` }} />
            {stage.removed ? <div className="cw-funnel-removed cw-num">重复 {stage.removed}</div> : null}
            {stage.removed_by_reason && Object.keys(stage.removed_by_reason).length ? (
              <div className="cw-funnel-removed">
                {Object.entries(stage.removed_by_reason)
                  .map(([k, v]) => `${SKIP_REASON_LABEL[k] ?? k} ${v}`)
                  .join(' · ')}
              </div>
            ) : null}
            {stage.key === 'triage' && stage.threshold !== undefined ? (
              <div className="cw-funnel-removed cw-num">过线 ≥ {stage.threshold}</div>
            ) : null}
            {stage.key === 'quick' && stage.passed !== undefined ? (
              <div className="cw-funnel-removed cw-num">值得完整分析 {stage.passed}</div>
            ) : null}
          </div>
        ))}
      </div>
      <div className="cw-cell-sub" style={{ marginTop: 10 }}>
        积压：待分析 <span className="cw-num">{funnel.backlog.pending}</span> · 分析中{' '}
        <span className="cw-num">{funnel.backlog.analyzing}</span> · 失败 <span className="cw-num">{funnel.backlog.error}</span>
      </div>
      <BudgetLine budget={funnel.budget} />
    </>
  );
}

function ActionLog({ items, onUndo }: { items: AutoActionItem[]; onUndo: (item: AutoActionItem) => void }) {
  if (!items.length) return <div className="cw-empty">还没有自动处理</div>;
  return (
    <ul className="cw-list">
      {items.map((item) => (
        <li key={item.id}>
          <StatusDot tone={actionTone(item)} />
          <div>
            <div>
              <span className="cw-cell-title">{item.target_label ?? item.target_id}</span>
              <span className="cw-muted"> · {ACTION_LABEL[item.action_type] ?? item.action_type}</span>
            </div>
            <div className="cw-cell-sub">{item.reason}</div>
            <div className="cw-cell-sub cw-num">
              {relativeTime(item.executed_at)}
              {item.undone_at ? ` · 已撤销` : ''}
            </div>
          </div>
          {item.undoable ? (
            <Button variant="ghost" icon={<Undo2 />} onClick={() => onUndo(item)}>
              撤销
            </Button>
          ) : (
            <span />
          )}
        </li>
      ))}
    </ul>
  );
}

export default function SourcesCollectionPage() {
  const [overview, setOverview] = useState<CollectionOverview | null>(null);
  const [rows, setRows] = useState<SourceHealthRow[]>([]);
  const [funnel, setFunnel] = useState<CollectionFunnel | null>(null);
  const [actions, setActions] = useState<AutoActionItem[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busy, setBusy] = useState<Set<number>>(new Set());
  const [platforms, setPlatforms] = useState<PlatformInfo[]>([]);
  const [adding, setAdding] = useState(false);
  const [funnelSettingsOpen, setFunnelSettingsOpen] = useState(false);
  const [recentSource, setRecentSource] = useState<SourceHealthRow | null>(null);
  const [toast, toastHolder] = message.useMessage();

  const load = useCallback(async () => {
    try {
      const [ov, health, fn, acts, plats] = await Promise.all([
        collectionApi.overview(),
        collectionApi.health(),
        collectionApi.funnel(7),
        collectionApi.autoActions(30),
        collectionApi.platforms(),
      ]);
      setPlatforms(plats.items);
      setOverview(ov);
      setRows(health.sources);
      setFunnel(fn);
      setActions(acts.items);
      setLoadError(null);
    } catch (err) {
      setLoadError(errorText(err));
    }
  }, []);

  useEffect(() => {
    load();
    const timer = window.setInterval(load, 60_000);
    return () => window.clearInterval(timer);
  }, [load]);

  const problemCount = useMemo(
    () => rows.filter((r) => r.enabled && ['paused', 'error', 'stale', 'empty'].includes(r.state)).length,
    [rows],
  );

  const onSync = async (row: SourceHealthRow) => {
    setBusy((prev) => new Set(prev).add(row.id));
    try {
      const res = await collectionApi.syncSource(row.id);
      if (res.status === 'failed') toast.error(`${row.name}：${ERROR_KIND_LABEL[res.error_kind || 'other'] ?? '失败'}`);
      else toast.success(`${row.name}：新增 ${res.new ?? 0} 条`);
    } catch (err) {
      toast.error(errorText(err));
    } finally {
      setBusy((prev) => {
        const next = new Set(prev);
        next.delete(row.id);
        return next;
      });
      load();
    }
  };

  const onToggle = async (row: SourceHealthRow) => {
    try {
      await collectionApi.updateSource(row.id, { enabled: !row.enabled });
      load();
    } catch (err) {
      toast.error(errorText(err));
    }
  };

  const onInterval = async (row: SourceHealthRow, minutes: number) => {
    try {
      await collectionApi.updateSource(row.id, { interval_minutes: minutes });
      load();
    } catch (err) {
      toast.error(errorText(err));
    }
  };

  const onUndo = async (item: AutoActionItem) => {
    try {
      await collectionApi.undo(item.id);
      toast.success('已撤销');
      load();
    } catch (err) {
      toast.error(errorText(err));
    }
  };

  const onPause = async () => {
    if (!overview) return;
    try {
      await collectionApi.setPaused(!overview.paused);
      load();
    } catch (err) {
      toast.error(errorText(err));
    }
  };

  return (
    <CwPage>
      {toastHolder}
      <TopBar title="信源">
        <nav className="cw-seg" aria-label="信源分页">
          {TABS.map((tab) => (
            <Link key={tab.href} href={tab.href} aria-current={tab.href === '/sources' ? 'page' : undefined}>
              {tab.label}
            </Link>
          ))}
        </nav>
        <span className="cw-health">
          <StatusDot tone={overview?.paused ? 'warn' : problemCount ? 'bad' : 'ok'} />
          {overview?.paused ? '采集已暂停' : problemCount ? `${problemCount} 个信源需要处理` : '采集正常'}
        </span>
        <Button icon={overview?.paused ? <Play /> : <Pause />} onClick={onPause} disabled={!overview}>
          {overview?.paused ? '恢复采集' : '暂停采集'}
        </Button>
        <Button variant="primary" icon={<Plus />} onClick={() => setAdding(true)}>
          添加信源
        </Button>
      </TopBar>

      {loadError ? <div className="cw-error">{loadError}</div> : null}

      <div className="cw-kpis" aria-label="关键数字">
        <Kpi label="今日新增" pair={overview?.today_new} />
        <Kpi label="7 天同步成功率" pair={overview?.success_rate_7d} suffix="%" />
        <Kpi label="待分析" pair={overview?.pending_analysis} higherIsBetter={false} />
        <Kpi label="今日分析花费" pair={overview?.analysis_cost_today} digits={2} suffix=" 元" higherIsBetter={false} />
        <Kpi label="漏采" pair={overview?.missed} higherIsBetter={false} />
      </div>

      <SuggestionsCard onChanged={load} onAddSource={() => setAdding(true)} />

      <SectionHead title="健康" note="异常排在最前" />
      <Card className="cw-scroll-x">
        <HealthTable
          rows={rows}
          busy={busy}
          onSync={onSync}
          onToggle={onToggle}
          onInterval={onInterval}
          onOpen={setRecentSource}
        />
      </Card>

      <div className="cw-grid-2">
        <div>
          <SectionHead title="流程" note="近 7 天">
            <Button variant="ghost" icon={<Settings2 />} onClick={() => setFunnelSettingsOpen(true)}>
              预算与阈值
            </Button>
          </SectionHead>
          <Card>
            <Funnel funnel={funnel} />
          </Card>
          <SectionHead title="平台" note="接口能力与 Key" />
          <Card>
            <PlatformList items={platforms} onChanged={(msg) => { toast.info(msg); load(); }} />
          </Card>
        </div>
        <div>
          <SectionHead title="处理记录" note="自动执行，可撤销" />
          <Card>
            <ActionLog items={actions} onUndo={onUndo} />
          </Card>
        </div>
      </div>

      <InsightsSections />

      <AddSourceModal
        open={adding}
        onClose={() => setAdding(false)}
        onAdded={(msg) => { toast.success(msg); load(); }}
        searchable={platforms}
      />
      <FunnelSettingsModal open={funnelSettingsOpen} onClose={() => setFunnelSettingsOpen(false)} onSaved={load} />
      <RecentDrawer source={recentSource} onClose={() => setRecentSource(null)} />
    </CwPage>
  );
}
