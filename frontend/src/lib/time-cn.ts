/**
 * 全站时间显示统一按北京时间（Asia/Shanghai，无夏令时，固定 UTC+8）。
 * 后端的「今天」窗口也是北京时间 0–24 点；浏览器在别的时区时，前端刻度和日期必须跟后端一致。
 */

export const CN_TZ = 'Asia/Shanghai';
export const CN_OFFSET_MS = 8 * 3600 * 1000;

/** 北京时间的「墙上时间」各分量。 */
export function cnParts(at: Date | string | number): { y: number; mo: number; d: number; h: number; mi: number; wd: number } {
  const t = new Date(new Date(at).getTime() + CN_OFFSET_MS);
  return { y: t.getUTCFullYear(), mo: t.getUTCMonth() + 1, d: t.getUTCDate(), h: t.getUTCHours(), mi: t.getUTCMinutes(), wd: t.getUTCDay() };
}

const pad = (n: number) => String(n).padStart(2, '0');
const WD = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];

export function fmtHM(at: Date | string | number): string {
  const p = cnParts(at);
  return `${pad(p.h)}:${pad(p.mi)}`;
}

/** 「10 月 21 日 周三」 */
export function fmtDay(at: Date | string | number): string {
  const p = cnParts(at);
  return `${p.mo} 月 ${p.d} 日 ${WD[p.wd]}`;
}

export function fmtMD(at: Date | string | number): string {
  const p = cnParts(at);
  return `${p.mo}/${p.d}`;
}
