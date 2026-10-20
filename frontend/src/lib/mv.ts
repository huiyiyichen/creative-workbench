/** 音乐 MV 时间轴的纯函数：分镜边界、拖动边界吸附歌词时间点。 */

export interface TimedShot {
  seconds: number;
}
export interface Cue {
  time: number;
  text: string;
}

/** 每镜起点（秒），最后一个是总时长。 */
export function boundaries(shots: TimedShot[]): number[] {
  const out = [0];
  for (const s of shots) out.push(round3(out[out.length - 1] + (Number(s.seconds) || 0)));
  return out;
}

export function round3(n: number): number {
  return Math.round(n * 1000) / 1000;
}

/** 最近的歌词时间点（在 snap 秒以内），没有就原样返回。 */
export function snapToCue(time: number, cues: Cue[], snap = 0.5): number {
  let best = time;
  let dist = snap;
  for (const c of cues) {
    const d = Math.abs(c.time - time);
    if (d <= dist) {
      best = c.time;
      dist = d;
    }
  }
  return best;
}

/**
 * 把第 index 条边界（第 index 镜的起点，1..n-1）移到 time：前后两镜此消彼长，总时长不变；
 * 吸附到附近歌词，且每镜至少 0.5 秒。
 */
export function moveBoundary<T extends TimedShot>(shots: T[], index: number, time: number, cues: Cue[], snap = 0.5): T[] {
  if (index <= 0 || index >= shots.length) return shots;
  const b = boundaries(shots);
  const min = b[index - 1] + 0.5;
  const max = b[index + 1] - 0.5;
  if (min > max) return shots;
  const t = round3(Math.min(max, Math.max(min, snapToCue(time, cues, snap))));
  const next = shots.slice();
  next[index - 1] = { ...shots[index - 1], seconds: round3(t - b[index - 1]) };
  next[index] = { ...shots[index], seconds: round3(b[index + 1] - t) };
  return next;
}

/** 某时间点落在第几镜 */
export function shotAt(shots: TimedShot[], time: number): number {
  const b = boundaries(shots);
  for (let i = 0; i < shots.length; i++) if (time < b[i + 1]) return i;
  return Math.max(0, shots.length - 1);
}
