/** 热度相位图的几何：横轴 = 首次出现距今（小时，对数刻度），纵轴 = 近一段的热度变化率。 */

export type PhaseInput = { id: number; first_seen_at: string | null; signal: number | null; signal_prev: number | null; content_count: number };
export type PhasePoint = { id: number; x: number; y: number; r: number; age: number; change: number };

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

export function changeRate(signal: number | null, prev: number | null): number {
  if (signal === null) return 0;
  if (prev === null || prev <= 0) return signal > 0 ? PHASE_Y[1] : 0;
  return (signal - prev) / prev;
}

export function phasePoints(rows: PhaseInput[], now: number): PhasePoint[] {
  const maxN = Math.max(1, ...rows.map((r) => r.content_count));
  return rows
    .filter((r) => r.first_seen_at)
    .map((r) => {
      const age = (now - new Date(r.first_seen_at!).getTime()) / 3600000;
      const change = changeRate(r.signal, r.signal_prev);
      return { id: r.id, age, change, x: ageX(age), y: changeY(change), r: 3 + 7 * Math.sqrt(r.content_count / maxN) };
    });
}

/** y=0 变化率对应的纵向位置（「不变」水平线） */
export const ZERO_Y = changeY(0);
/** 24 小时竖线（左边算「新」） */
export const DAY_X = ageX(24);
