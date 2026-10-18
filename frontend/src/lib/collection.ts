/**
 * 采集页的纯展示逻辑（可在 node 里测）。
 */

import type { AutoActionItem, HealthState, MetricPair, SourceHealthRow } from '@/lib/api/_collection';
import type { Tone } from '@/design/components';

export const HEALTH_LABEL: Record<HealthState, string> = {
  paused: '已暂停',
  error: '失败',
  stale: '可能失效',
  empty: '连续 0 条',
  idle: '未同步',
  ok: '正常',
  disabled: '已停用',
};

export const HEALTH_TONE: Record<HealthState, Tone> = {
  paused: 'warn',
  error: 'bad',
  stale: 'warn',
  empty: 'warn',
  idle: 'off',
  ok: 'ok',
  disabled: 'off',
};

export const ERROR_KIND_LABEL: Record<string, string> = {
  login: '登录失效',
  captcha: '验证码',
  rate_limit: '限流',
  timeout: '超时',
  api_changed: '接口变化',
  blocked: '拒绝访问',
  other: '其他',
};

export const SKIP_REASON_LABEL: Record<string, string> = {
  short_text: '太短',
  self_promo: '自我推广',
  hard_low_signal: '低信号',
  no_body: '无正文',
  other: '其他',
};

export const ACTION_LABEL: Record<string, string> = {
  pause_source: '暂停信源',
  pause_platform: '暂停平台',
  backoff_source: '限流退避',
  flag_stale: '可能失效',
  resume_source: '自动恢复',
};

export function actionTone(action: AutoActionItem): Tone {
  if (action.undone_at) return 'off';
  if (action.action_type === 'resume_source') return 'ok';
  if (action.action_type === 'pause_source' || action.action_type === 'pause_platform') return 'bad';
  return 'warn';
}

/** 需要处理的信源（托盘与导航红点同口径） */
export function hasSourceProblems(rows: SourceHealthRow[]): boolean {
  return rows.some((r) => r.enabled && (r.state === 'paused' || r.state === 'error' || r.state === 'stale'));
}

export type DeltaDir = 'up' | 'down' | 'flat';

/** 与 7 天前对比；任一侧缺失时返回 null（不臆造变化） */
export function delta(pair: MetricPair, higherIsBetter = true): { text: string; dir: DeltaDir } | null {
  if (pair.value === null || pair.previous === null) return null;
  const diff = pair.value - pair.previous;
  if (Math.abs(diff) < 1e-9) return { text: '持平', dir: 'flat' };
  const good = diff > 0 === higherIsBetter;
  const abs = Math.abs(diff);
  const text = `${diff > 0 ? '+' : '−'}${Number.isInteger(abs) ? abs : abs.toFixed(1)}`;
  return { text, dir: good ? 'up' : 'down' };
}

/** 相对时间：「3 分钟前」「2 小时后」；缺失返回「—」 */
export function relativeTime(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return '—';
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return '—';
  const diffMin = Math.round((t - now.getTime()) / 60000);
  const abs = Math.abs(diffMin);
  const future = diffMin > 0;
  let body: string;
  if (abs < 1) return future ? '即将' : '刚刚';
  if (abs < 60) body = `${abs} 分钟`;
  else if (abs < 60 * 48) body = `${Math.round(abs / 60)} 小时`;
  else body = `${Math.round(abs / 1440)} 天`;
  return future ? `${body}后` : `${body}前`;
}

export function intervalLabel(minutes: number): string {
  if (minutes % 1440 === 0) return `${minutes / 1440} 天`;
  if (minutes % 60 === 0) return `${minutes / 60} 小时`;
  return `${minutes} 分钟`;
}

export const INTERVAL_OPTIONS = [30, 60, 120, 240, 360, 720, 1440];
