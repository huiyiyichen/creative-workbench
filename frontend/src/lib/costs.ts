/** 花费页的纯函数：金额格式、用途分组配色、堆叠柱几何。 */

import type { CostDay } from './api/_costs';

/** 用途分组 → 信号色（CSS 变量）。生成类用视频 / 图文色系，分析用文章黄。 */
export const GROUP_COLOR: Record<string, string> = {
  analysis: 'var(--cw-yl)',
  report: 'var(--cw-bl)',
  create: 'var(--cw-cy)',
  reading: 'var(--cw-gr)',
  gen_image: 'var(--cw-mg)',
  gen_video: 'var(--cw-rd)',
  gen_music: 'var(--cw-wh)',
  other: 'var(--cw-dim)',
};

export const GROUP_ORDER = ['analysis', 'report', 'create', 'reading', 'gen_image', 'gen_video', 'gen_music', 'other'];

export function groupColor(key: string): string {
  return GROUP_COLOR[key] ?? 'var(--cw-dim)';
}

/** ¥ 金额：≥100 取整，≥1 两位，<1 三位有效，0 显示 0 */
export function yuan(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  if (v === 0) return '¥0';
  if (Math.abs(v) >= 100) return `¥${Math.round(v).toLocaleString('zh-CN')}`;
  if (Math.abs(v) >= 1) return `¥${v.toFixed(2)}`;
  return `¥${Number(v.toPrecision(2))}`;
}

export type StackSeg = { key: string; y: number; h: number };

/** 每天一根堆叠柱：按 GROUP_ORDER 从下往上，高度按 max 归一到 height。 */
export function stackDays(series: CostDay[], height: number): { date: string; total: number; segs: StackSeg[] }[] {
  const max = Math.max(0, ...series.map((d) => d.total));
  return series.map((d) => {
    const segs: StackSeg[] = [];
    let y = height;
    if (max > 0) {
      const keys = [...GROUP_ORDER, ...Object.keys(d).filter((k) => k !== 'date' && k !== 'total' && !GROUP_ORDER.includes(k))];
      for (const k of keys) {
        const v = typeof d[k] === 'number' ? (d[k] as number) : 0;
        if (v <= 0) continue;
        const h = (v / max) * height;
        y -= h;
        segs.push({ key: k, y, h });
      }
    }
    return { date: d.date, total: d.total, segs };
  });
}

/** 相对 7 日均值的变化，用来给「今天」配涨跌色。 */
export function vsAvg(today: number, avg: number | null): { text: string; up: boolean } | null {
  if (avg === null || avg <= 0) return null;
  const r = (today - avg) / avg;
  return { text: `${r >= 0 ? '+' : ''}${Math.round(r * 100)}%`, up: r >= 0 };
}
