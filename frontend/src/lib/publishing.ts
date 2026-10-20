/** 发布日历的纯函数：北京时间的周窗口、按天分桶、指标数字缩写。 */

import { CN_OFFSET_MS, cnParts } from './time-cn';

const DAY = 24 * 3600 * 1000;

/** 包含 at 的那一周（周一 00:00 北京时间起）的 7 天起点（UTC 毫秒）。offset 为相对周数。 */
export function weekDays(at: Date | number, offset = 0): number[] {
  const t = new Date(at).getTime();
  const p = cnParts(t);
  const midnight = Math.floor((t + CN_OFFSET_MS) / DAY) * DAY - CN_OFFSET_MS;
  const sinceMon = (p.wd + 6) % 7;
  const mon = midnight - sinceMon * DAY + offset * 7 * DAY;
  return Array.from({ length: 7 }, (_, i) => mon + i * DAY);
}

export function bucketByDay<T extends { at?: string | null }>(items: T[], days: number[]): T[][] {
  const out: T[][] = days.map(() => []);
  for (const it of items) {
    if (!it.at) continue;
    const t = new Date(it.at).getTime();
    const i = days.findIndex((d) => t >= d && t < d + DAY);
    if (i >= 0) out[i].push(it);
  }
  return out;
}

/** 1234 → 1234；12345 → 1.2 万；1.2e8 → 1.2 亿 */
export function compactNum(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  if (v >= 1e8) return `${(v / 1e8).toFixed(1).replace(/\.0$/, '')} 亿`;
  if (v >= 1e4) return `${(v / 1e4).toFixed(1).replace(/\.0$/, '')} 万`;
  return String(Math.round(v));
}

/** datetime-local 输入框值（北京时间）↔ ISO */
export function toLocalInput(iso: string | null | undefined): string {
  if (!iso) return '';
  const p = cnParts(iso);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${p.y}-${pad(p.mo)}-${pad(p.d)}T${pad(p.h)}:${pad(p.mi)}`;
}

export function fromLocalInput(v: string): string | null {
  if (!v) return null;
  const d = new Date(`${v}:00+08:00`);
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}
