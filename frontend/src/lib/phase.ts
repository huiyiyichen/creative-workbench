/** 热度相位图的几何：横轴 = 首次出现距今（小时，对数刻度），纵轴 = 近一段的热度变化率。 */

export type PhaseInput = { id: number; first_seen_at: string | null; signal: number | null; signal_prev: number | null; content_count: number };
export type PhasePoint = { id: number; x: number; y: number; r: number; age: number; change: number | null; first: boolean; over: boolean };

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
export const BAND = 0.16; // 顶部「首次观测」带的高度（两行错位避让）
/** 右侧「>7 天」单独一列的宽度（评审 #3 1.2-2：超过 7 天的点不再叠在右边界上） */
export const OVER_W = 0.05;
export function plotX(x: number): number {
  return PAD_X + (1 - 2 * PAD_X - OVER_W) * x;
}
/** 「>7 天」列的中心 */
export const OVER_X = 1 - PAD_X / 2 - OVER_W / 2;
export function plotY(y: number): number {
  return BAND + 0.04 + (1 - BAND - 0.1) * y;
}

/**
 * 计算点位。两处一维避让（评审 #3 1.2-1/2）：
 * - 首次观测带：按 x 排序，和前一个点横向距离 < minDx 时换到另一行（两行错位）；
 * - 「>7 天」列：按 y 排序，纵向距离 < minDy 时往下推。
 * minDx / minDy 是 0..1 的归一化距离（默认约 10px / 1000px 宽、9px / 260px 高）。
 */
export function phasePoints(rows: PhaseInput[], now: number, minDx = 0.012, minDy = 0.035): PhasePoint[] {
  const maxN = Math.max(1, ...rows.map((r) => r.content_count));
  const pts: PhasePoint[] = rows
    .filter((r) => r.first_seen_at)
    .map((r) => {
      const age = (now - new Date(r.first_seen_at!).getTime()) / 3600000;
      const change = changeRate(r.signal, r.signal_prev);
      const first = change === null;
      const over = age > PHASE_MAX_H;
      return {
        id: r.id,
        age,
        change,
        first,
        over,
        x: over ? OVER_X : plotX(ageX(age)),
        y: first ? BAND / 2 : plotY(changeY(change)),
        r: 3 + 7 * Math.sqrt(r.content_count / maxN),
      };
    });
  // 首次观测带：两行，各有一个「已占到哪」的游标；每个点放进挪动最少的那一行，
  // 同一时刻冒出的一批点会向右铺开成一串，而不是叠成一个（评审 #3 1.2-1）
  const band = pts.filter((p) => p.first && !p.over).sort((a, b) => a.x - b.x);
  const cursor = [-1, -1];
  const limit = plotX(1);
  for (const p of band) {
    const want = [Math.max(p.x, cursor[0] + minDx), Math.max(p.x, cursor[1] + minDx)];
    const row = want[1] < want[0] ? 1 : 0;
    p.x = Math.min(limit, want[row]);
    p.y = BAND * (row ? 0.7 : 0.32);
    cursor[row] = p.x;
  }
  // 「>7 天」的首次观测点：在窄列里按网格排开（两行 × 列内可容纳的个数），不再叠成一团（评审 #4 P1-3）
  const perRow = Math.max(1, Math.floor(OVER_W / minDx));
  pts
    .filter((p) => p.first && p.over)
    .forEach((p, i) => {
      const row = Math.floor(i / perRow) % 2;
      const k = i % perRow;
      p.x = OVER_X - OVER_W / 2 + (k + 0.5) * (OVER_W / perRow);
      p.y = BAND * (row ? 0.7 : 0.32);
    });
  // 「>7 天」列：按 y 排序，纵向间距至少两点半径之和（按 260px 高换算），放不下就左右错开
  const col = pts.filter((p) => p.over && !p.first).sort((a, b) => a.y - b.y);
  for (let i = 1; i < col.length; i++) {
    const need = Math.max(minDy, (col[i].r + col[i - 1].r + 2) / 260);
    if (col[i].y - col[i - 1].y < need) {
      if (col[i - 1].y + need > 0.98) col[i].x = OVER_X + (i % 2 ? -1 : 1) * OVER_W * 0.3;
      col[i].y = Math.min(0.98, col[i - 1].y + need);
    }
  }
  return pts;
}

/** y=0 变化率对应的纵向位置（「不变」水平线） */
export const ZERO_Y = plotY(changeY(0));
/** 24 小时竖线（左边算「新」） */
export const DAY_X = plotX(ageX(24));
