/** 热度相位图的几何：横轴 = 首次出现距今（小时，对数刻度），纵轴 = 近一段的热度变化率。 */

export type PhaseInput = { id: number; first_seen_at: string | null; signal: number | null; signal_prev: number | null; content_count: number };
export type PhasePoint = { id: number; x: number; y: number; r: number; age: number; change: number | null; first: boolean };

export const PHASE_MAX_H = 168; // 7 天
export const PHASE_Y = [-1, 2] as const; // 变化率 -100% … +200%

/** 小时 → 0..1（log1p 刻度，7 天封顶） */
export function ageX(hours: number): number {
  const h = Math.max(0, Math.min(PHASE_MAX_H, hours));
  return Math.log1p(h) / Math.log1p(PHASE_MAX_H);
}

/** 变化率 → 0..1（上方为升温） */
export function changeY(rate: number): number {
  const [lo, hi] = PHASE_Y;
  const r = Math.max(lo, Math.min(hi, rate));
  return 1 - (r - lo) / (hi - lo);
}

/** 变化率；没有上一次观测时返回 null（首次观测，单独画在顶部一条带里） */
export function changeRate(signal: number | null, prev: number | null): number | null {
  if (signal === null) return 0;
  if (prev === null || prev <= 0) return signal > 0 ? null : 0;
  return (signal - prev) / prev;
}

/** 画布内边距：点不贴边、不被裁 */
export const PAD_X = 0.04;
export const BAND = 0.12; // 顶部「首次观测」带的高度
export function plotX(x: number): number {
  return PAD_X + (1 - 2 * PAD_X) * x;
}
export function plotY(y: number): number {
  return BAND + 0.04 + (1 - BAND - 0.1) * y;
}

export function phasePoints(rows: PhaseInput[], now: number): PhasePoint[] {
  const maxN = Math.max(1, ...rows.map((r) => r.content_count));
  return rows
    .filter((r) => r.first_seen_at)
    .map((r) => {
      const age = (now - new Date(r.first_seen_at!).getTime()) / 3600000;
      const change = changeRate(r.signal, r.signal_prev);
      const first = change === null;
      return { id: r.id, age, change, first, x: plotX(ageX(age)), y: first ? BAND / 2 : plotY(changeY(change)), r: 3 + 7 * Math.sqrt(r.content_count / maxN) };
    });
}

/** y=0 变化率对应的纵向位置（「不变」水平线） */
export const ZERO_Y = plotY(changeY(0));
/** 24 小时竖线（左边算「新」） */
export const DAY_X = plotX(ageX(24));
