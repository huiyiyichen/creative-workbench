import { CN_OFFSET_MS, cnParts } from './time-cn';
/**
 * 发现页面的展示逻辑（纯函数，便于测试）：结论标记、话题状态、时间线定位、指标示波、带缺口的曲线。
 */
import { color, mediaColor } from '@/design/tokens';
import type { MetricView, TopicStatus, Verdict } from '@/lib/api/_discover';
import { METRIC_LABEL, compactNumber, relativeTime } from '@/lib/collection';

export const VERDICT_LABEL: Record<Verdict, string> = { worth: '值得做', watch: '观察', skip: '跳过' };
export const VERDICT_COLOR: Record<Verdict, string> = { worth: color.gr, watch: color.yl, skip: color.faint };

export const STATUS_LABEL: Record<TopicStatus, string> = {
  new: '新出现',
  rising: '升温',
  steady: '持续',
  peak: '见顶',
  cooling: '降温',
  quiet: '平静',
};
export const STATUS_COLOR: Record<TopicStatus, string> = {
  new: color.cy,
  rising: color.rd,
  steady: color.yl,
  peak: color.mg,
  cooling: color.bl,
  quiet: color.faint,
};

export const MEDIA_LABEL: Record<string, string> = {
  article: '文章',
  video: '视频',
  image: '图文',
  post: '帖子',
  prompt: '提示词',
  repo: '仓库',
  list: '榜单',
};

export const MEDIA_FILTERS: { value: string; label: string }[] = [
  { value: '', label: '全部' },
  { value: 'video', label: '视频' },
  { value: 'article', label: '文章' },
  { value: 'image', label: '图文' },
  { value: 'post', label: '帖子' },
  { value: 'prompt', label: '提示词' },
  { value: 'repo', label: '仓库' },
];

export function mediaKindColor(kind: string | null | undefined): string {
  if (kind === 'post') return mediaColor.article;
  return (mediaColor as Record<string, string>)[kind || 'article'] ?? mediaColor.article;
}

/** 时间线上的横向位置（0–1）：按当天 0 点到 24 点 */
export function dayPosition(at: string, dayStart: string, dayEnd: string): number {
  const t = new Date(at).getTime();
  const s = new Date(dayStart).getTime();
  const e = new Date(dayEnd).getTime();
  if (!(e > s)) return 0;
  return Math.min(1, Math.max(0, (t - s) / (e - s)));
}

export type SignalRange = 'today' | '48h' | '7d';
export const SIGNAL_RANGES: { value: SignalRange; label: string }[] = [
  { value: 'today', label: '今天' },
  { value: '48h', label: '48 小时' },
  { value: '7d', label: '7 天' },
];
export const SIGNAL_TITLE: Record<SignalRange, string> = { today: '今天的信号', '48h': '近 48 小时的信号', '7d': '近 7 天的信号' };

/**
 * 时间轴刻度（按本地时间）：今天每 3 小时；48 小时每 6 小时、零点换成日期；7 天每个零点一格写日期。
 * pos 是 0–1 的位置，只返回落在窗口内的刻度。
 */
export function rulerTicks(range: SignalRange | 'zoom', start: string, end: string): { pos: number; label: string }[] {
  const s = new Date(start).getTime();
  const e = new Date(end).getTime();
  if (!(e > s)) return [];
  const H = 3600 * 1000;
  const spanH = (e - s) / H;
  const stepH = range === 'zoom' ? (spanH <= 12 ? 1 : 3) : range === 'today' ? 3 : range === '48h' ? 6 : 24;
  // 北京时间整点：先把起点推到「北京时间能被 stepH 整除的整点」
  let t = Math.ceil((s + CN_OFFSET_MS) / H) * H - CN_OFFSET_MS;
  while (cnParts(t).h % stepH !== 0) t += H;
  const out: { pos: number; label: string }[] = [];
  for (; t <= e; t += stepH * H) {
    const p = cnParts(t);
    const label = range === 'today' || range === 'zoom' ? `${String(p.h).padStart(2, '0')}:00` : p.h === 0 ? `${p.mo}/${p.d}` : `${String(p.h).padStart(2, '0')}:00`;
    out.push({ pos: (t - s) / (e - s), label });
  }
  return out;
}

/** 热度 → 亮度（不透明度）：没有平台指标时用中等亮度 */
export function heatOpacity(heat: number | null | undefined): number {
  if (heat === null || heat === undefined) return 0.45;
  return Math.round((0.3 + 0.7 * Math.min(1, Math.max(0, heat))) * 100) / 100;
}

/** 指标示波文字：原始值、变化量、观测时间；RSS 显示「RSS 无平台指标」 */
export function metricText(m: MetricView, now: Date = new Date()): { label: string; value: string; delta: string | null; observed: string | null } {
  if (!m.metric) return { label: '', value: m.state || '无平台指标', delta: null, observed: null };
  const label = METRIC_LABEL[m.metric] || m.metric;
  if (m.metric === 'rank') {
    return { label: '排名', value: `第 ${m.value}`, delta: null, observed: m.observed_at ? `${relativeTime(m.observed_at, now)}观测` : null };
  }
  const d = m.delta;
  return {
    label,
    value: compactNumber(m.value ?? null),
    delta: d === null || d === undefined ? null : `${d >= 0 ? '+' : ''}${compactNumber(d)}`,
    observed: m.observed_at ? `${relativeTime(m.observed_at, now)}观测` : null,
  };
}

/**
 * 带缺口的曲线：null 表示观测不足，断开不画（不画 0）。返回若干段 path。
 * 少于 2 个有效点返回空数组。
 */
export function gappedPaths(values: (number | null)[], width: number, height: number, pad = 2): string[] {
  const known = values.filter((v): v is number => v !== null);
  if (known.length < 2) return [];
  const min = Math.min(...known);
  const max = Math.max(...known);
  const span = max - min;
  const step = values.length > 1 ? (width - pad * 2) / (values.length - 1) : 0;
  const paths: string[] = [];
  let cur: string[] = [];
  values.forEach((v, i) => {
    if (v === null) {
      if (cur.length >= 2) paths.push(cur.join(' '));
      cur = [];
      return;
    }
    const x = pad + i * step;
    const y = span === 0 ? height / 2 : height - pad - ((v - min) / span) * (height - pad * 2);
    cur.push(`${cur.length === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`);
  });
  if (cur.length >= 2) paths.push(cur.join(' '));
  return paths;
}

/** 逐小时序列按 n 小时合并（求和，整段都是 null 时为 null） */
export function bucketSeries(values: (number | null)[], n: number): (number | null)[] {
  const out: (number | null)[] = [];
  for (let i = 0; i < values.length; i += n) {
    const chunk = values.slice(i, i + n);
    const known = chunk.filter((v): v is number => v !== null);
    out.push(known.length ? known.reduce((a, b) => a + b, 0) : null);
  }
  return out;
}

/** 平台分布排序后的前 n 个 */
export function topPlatforms(dist: Record<string, number>, n = 4): [string, number][] {
  return Object.entries(dist)
    .sort((a, b) => b[1] - a[1])
    .slice(0, n);
}

/** 本地日期字符串 YYYY-MM-DD（Asia/Shanghai 由浏览器时区决定，本应用在本机运行） */
export function localDate(d: Date = new Date()): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

/** 日历网格：周一开头，前后补空格 */
export function monthGrid(year: number, month: number): (string | null)[] {
  const first = new Date(year, month - 1, 1);
  const days = new Date(year, month, 0).getDate();
  const lead = (first.getDay() + 6) % 7;
  const cells: (string | null)[] = Array(lead).fill(null);
  for (let d = 1; d <= days; d += 1) cells.push(localDate(new Date(year, month - 1, d)));
  while (cells.length % 7) cells.push(null);
  return cells;
}

export const JOURNEY_LABEL: Record<string, string> = {
  collected: '采集',
  prefilter: '预筛',
  triage: '初筛',
  event: '归并',
  quick: '快速判断',
  full: '完整分析',
  verdict: '结论',
  favorited: '收藏',
  used_in_project: '用于项目',
  in_work: '进入成片',
};

export const BASIS_LABEL: Record<string, string> = {
  heat: '热度',
  timing: '时机',
  same_topic: '同题',
  relevance: '和你相关',
  quality: '内容质量',
  quick: '快速判断',
};

export function percent(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—';
  return `${Math.round(v * 100)}%`;
}
