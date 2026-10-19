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

// ── 阶段 1：信源类型、平台、观测曲线 ──────────────────────────────

export const KIND_LABEL: Record<string, string> = {
  subscription: '订阅',
  keyword: '追踪词',
  list: '榜单',
};

export const PLATFORM_LABEL: Record<string, string> = {
  bilibili: 'B站',
  youtube: 'YouTube',
  github: 'GitHub',
  hn: 'HN',
  reddit: 'Reddit',
  douyin: '抖音',
  xiaohongshu: '小红书',
  zhihu: '知乎',
  web: '网页',
  multi: '多平台',
};

export const METRIC_LABEL: Record<string, string> = {
  views: '播放',
  likes: '点赞',
  comments: '评论',
  favorites: '收藏',
  shares: '转发',
  coins: '投币',
  danmaku: '弹幕',
  stars: 'Star',
  forks: 'Fork',
  score: '分数',
  hot: '热度',
  rank: '排名',
};

/** 观测曲线优先展示的指标（排名不画曲线） */
const SERIES_PRIORITY = ['views', 'stars', 'score', 'likes', 'hot', 'comments', 'favorites'];

export function primarySeries(series: Record<string, { at: string; value: number }[]>): string | null {
  for (const key of SERIES_PRIORITY) if ((series[key]?.length ?? 0) > 0) return key;
  return Object.keys(series).find((k) => k !== 'rank') ?? null;
}

/** 折线坐标：至少 2 个点才画；不足返回 null（界面显示「暂无历史观测」，不画 0） */
export function sparkPath(values: number[], width: number, height: number, pad = 2): string | null {
  if (values.length < 2) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min;
  const step = (width - pad * 2) / (values.length - 1);
  return values
    .map((v, i) => {
      const x = pad + i * step;
      // 全部相同的值画在中线（持平），不贴底，避免看成 0
      const y = span === 0 ? height / 2 : height - pad - ((v - min) / span) * (height - pad * 2);
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');
}

/** 61 → "1:01"；3723 → "1:02:03" */
export function formatDuration(seconds: number | null | undefined): string | null {
  if (seconds === null || seconds === undefined || seconds < 0) return null;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  const mm = h ? String(m).padStart(2, '0') : String(m);
  return `${h ? `${h}:` : ''}${mm}:${String(s).padStart(2, '0')}`;
}

/** 大数字：12345 → "1.2万" */
export function compactNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  if (Math.abs(value) >= 1e8) return `${(value / 1e8).toFixed(1)}亿`;
  if (Math.abs(value) >= 1e4) return `${(value / 1e4).toFixed(1)}万`;
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

/** 生成封面的波形：按标题稳定生成（同一标题每次一样） */
export function waveform(seed: string, points = 32): number[] {
  let h = 2166136261;
  for (const ch of seed) h = Math.imul(h ^ ch.codePointAt(0)!, 16777619) >>> 0;
  const out: number[] = [];
  for (let i = 0; i < points; i += 1) {
    h = Math.imul(h ^ (h >>> 13), 1274126177) >>> 0;
    const noise = (h % 1000) / 1000;
    out.push(0.5 + 0.35 * Math.sin(i / 2.3 + noise * 2) * (0.4 + noise * 0.6));
  }
  return out;
}

export function analysisLabel(item: { analysis_level: string; full_eligible: boolean | null }): string {
  if (item.analysis_level === 'full') return '已分析';
  if (item.full_eligible === false) return '不做完整分析';
  if (item.analysis_level === 'quick') return '待完整分析';
  return '未分析';
}
