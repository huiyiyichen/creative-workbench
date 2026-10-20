/**
 * 无封面时的「信号图」：按标题哈希确定性地生成，同一标题永远同一张图。
 * 每种内容形态一种图形语汇（照样张的示波器风格往外延伸）：
 *   视频 = 双迹示波 + 播放进度；文章 = 段落条 + 低幅迹线；图文 = 三张错位卡片；
 *   提示词 = 终端行 + 光标；仓库 = 提交图；榜单 = 排名柱；其他 = 单迹示波。
 * 只出几何数据（viewBox 160×90），渲染在 design/signal-art.tsx。
 */

export const ART_W = 160;
export const ART_H = 90;

export function hashStr(s: string): number {
  let h = 2166136261;
  for (const ch of s) h = Math.imul(h ^ ch.codePointAt(0)!, 16777619);
  return h >>> 0;
}

/** Park–Miller 最小标准随机数，确定性。 */
export function seeded(seed: number): () => number {
  let x = seed % 2147483647;
  if (x <= 0) x += 2147483646;
  return () => (x = (x * 16807) % 2147483647) / 2147483647;
}

/** 平滑迹线（样张 scopeCover 的做法：正弦 + 小噪声），返回 SVG path。 */
export function tracePath(seed: number, opts: { base: number; amp: number; freq: number; noise: number; step?: number; x0?: number; x1?: number }): string {
  const r = seeded(seed);
  const { base, amp, freq, noise, step = 4, x0 = 0, x1 = ART_W - 4 } = opts;
  const phase = (seed % 97) / 10;
  const pts: string[] = [];
  for (let x = x0; x <= x1; x += step) {
    const y = base + Math.sin(x / freq + phase) * amp * (0.55 + 0.45 * r()) + (r() - 0.5) * noise;
    pts.push(`${pts.length ? 'L' : 'M'}${x.toFixed(1)},${Math.max(2, Math.min(ART_H - 2, y)).toFixed(1)}`);
  }
  return pts.join(' ');
}

export type ArtKind = 'video' | 'article' | 'image' | 'prompt' | 'repo' | 'list' | 'other';

export function artKind(kind: string | null | undefined): ArtKind {
  switch (kind) {
    case 'video':
    case 'mv':
      return 'video';
    case 'article':
    case 'wechat':
    case 'zhihu':
      return 'article';
    case 'image':
    case 'post':
    case 'xhs':
      return 'image';
    case 'prompt':
    case 'prompt_bundle':
      return 'prompt';
    case 'repo':
      return 'repo';
    case 'list':
    case 'hot':
      return 'list';
    default:
      return 'other';
  }
}

export type ArtSpec = {
  traces: { d: string; strong: boolean }[];
  rects: { x: number; y: number; w: number; h: number; o: number }[];
  dots: { x: number; y: number; r: number }[];
  lines: { x1: number; y1: number; x2: number; y2: number }[];
  progress?: number;
};

export function artSpec(title: string, kind: ArtKind): ArtSpec {
  const seed = hashStr(title || '·');
  const r = seeded(seed);
  const spec: ArtSpec = { traces: [], rects: [], dots: [], lines: [] };
  switch (kind) {
    case 'video': {
      // 标题哈希同时决定基线、振幅、频率，同形态的封面也一眼能分开
      spec.traces.push({ d: tracePath(seed + 7, { base: 44 + r() * 14, amp: 6 + r() * 8, freq: 10 + r() * 6, noise: 5 }), strong: false });
      spec.traces.push({ d: tracePath(seed, { base: 30 + r() * 24, amp: 9 + r() * 14, freq: 6 + r() * 8, noise: 4 + r() * 8 }), strong: true });
      spec.progress = 0.2 + r() * 0.6;
      break;
    }
    case 'article': {
      const lines = 3 + Math.floor(r() * 4);
      const twoCol = r() > 0.6;
      const colW = twoCol ? (ART_W - 36) / 2 : ART_W - 24;
      let y = 22 + r() * 8;
      for (let i = 0; i < lines; i += 1) {
        const w = i === 0 ? colW * (0.5 + r() * 0.4) : colW * (0.65 + r() * 0.35);
        spec.rects.push({ x: 12, y, w, h: i === 0 ? 6 : 3, o: i === 0 ? 0.55 : 0.18 + r() * 0.12 });
        if (twoCol && i > 0) spec.rects.push({ x: 24 + colW, y, w: colW * (0.5 + r() * 0.5), h: 3, o: 0.14 + r() * 0.1 });
        y += i === 0 ? 12 : 8;
      }
      spec.traces.push({ d: tracePath(seed, { base: Math.max(y + 10, 62 + r() * 18), amp: 3 + r() * 9, freq: 8 + r() * 8, noise: 2 + r() * 4 }), strong: true });
      break;
    }
    case 'image': {
      for (let k = 0; k < 3; k += 1) {
        spec.rects.push({ x: 14 + k * 46 + (r() - 0.5) * 4, y: 14 + (k % 2) * 6, w: 40, h: 58, o: 0.1 + k * 0.08 });
      }
      spec.traces.push({ d: tracePath(seed, { base: 58, amp: 10, freq: 10, noise: 4 }), strong: true });
      break;
    }
    case 'prompt': {
      let y = 20;
      for (let i = 0; i < 5; i += 1) {
        const indent = i === 0 ? 0 : Math.floor(r() * 3) * 8;
        const w = 30 + r() * 80;
        spec.rects.push({ x: 22 + indent, y, w, h: 3, o: i === 0 ? 0.6 : 0.22 });
        spec.dots.push({ x: 14, y: y + 1.5, r: 1.3 });
        y += 12;
      }
      const last = spec.rects[spec.rects.length - 1];
      spec.rects.push({ x: last.x + last.w + 4, y: last.y - 3, w: 5, h: 9, o: 0.9 });
      break;
    }
    case 'repo': {
      let x = 16;
      let lane = 1;
      const ys = [30, 45, 60];
      let prev = { x, y: ys[lane] };
      while (x < ART_W - 16) {
        x += 12 + r() * 12;
        if (r() < 0.3) lane = Math.max(0, Math.min(2, lane + (r() < 0.5 ? -1 : 1)));
        const pt = { x: Math.min(x, ART_W - 14), y: ys[lane] };
        spec.lines.push({ x1: prev.x, y1: prev.y, x2: pt.x, y2: pt.y });
        spec.dots.push({ x: pt.x, y: pt.y, r: 2.4 });
        prev = pt;
      }
      spec.dots.unshift({ x: 16, y: ys[1], r: 2.4 });
      break;
    }
    case 'list': {
      const n = 6;
      for (let i = 0; i < n; i += 1) {
        const w = (ART_W - 40) * (1 - i * 0.13) * (0.85 + r() * 0.15);
        spec.rects.push({ x: 26, y: 12 + i * 12, w, h: 6, o: i === 0 ? 0.85 : 0.5 - i * 0.06 });
        spec.dots.push({ x: 16, y: 15 + i * 12, r: 1.4 });
      }
      break;
    }
    default:
      spec.traces.push({ d: tracePath(seed, { base: 45, amp: 14, freq: 10, noise: 6 }), strong: true });
  }
  return spec;
}
