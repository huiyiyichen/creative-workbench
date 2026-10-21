/** 创作人格分享卡：1080×1920 竖版 SVG（导出 PNG 用）。分享出去的是图片，所以颜色写死为暗色仪器风，不跟主题。 */

import type { CreatorPersona } from './api/_digests';

export const CARD_W = 1080;
export const CARD_H = 1920;

const C = {
  bg: '#14171c',
  grid: '#1f242c',
  line: '#333b48',
  text: '#e8eaed',
  dim: '#8d96a3',
  faint: '#5e6774',
  yl: '#e3cc4b',
  cy: '#4fd2e2',
  mg: '#df5bd5',
  bl: '#6f8bff',
  gr: '#6ccf68',
};
const DOT = [C.yl, C.cy, C.mg, C.bl, C.gr];
const SANS = `'Noto Sans SC','PingFang SC','Microsoft YaHei',sans-serif`;
const SERIF = `'Noto Serif SC','Songti SC','SimSun',serif`;

export function esc(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

/** 按视觉宽度折行：汉字算 1，ASCII 算 0.55。 */
export function wrap(text: string, width: number, maxLines = 3): string[] {
  const lines: string[] = [];
  let cur = '';
  let w = 0;
  for (const ch of text) {
    const cw = /[\x00-\x7f]/.test(ch) ? 0.55 : 1;
    if (w + cw > width && cur) {
      lines.push(cur);
      cur = '';
      w = 0;
      if (lines.length === maxLines) break;
    }
    cur += ch;
    w += cw;
  }
  if (cur && lines.length < maxLines) lines.push(cur);
  else if (lines.length === maxLines && lines.join('').length < [...text].length) lines[maxLines - 1] = lines[maxLines - 1].slice(0, -1) + '…';
  return lines;
}

export function monthLabel(month: string): string {
  const [y, m] = month.split('-');
  return `${y} 年 ${Number(m)} 月`;
}

export function buildPersonaSvg(p: CreatorPersona, opts: { vote?: string; author?: string } = {}): string {
  const s = p.stats;
  const out: string[] = [];
  const t = (x: number, y: number, size: number, fill: string, text: string, extra = '') =>
    out.push(`<text x="${x}" y="${y}" font-size="${size}" fill="${fill}" font-family="${SANS}" ${extra}>${esc(text)}</text>`);

  out.push(`<rect width="${CARD_W}" height="${CARD_H}" fill="${C.bg}"/>`);
  for (let y = 96; y < CARD_H; y += 96) out.push(`<line x1="0" y1="${y}" x2="${CARD_W}" y2="${y}" stroke="${C.grid}" stroke-width="1"/>`);
  out.push(`<rect x="60" y="60" width="${CARD_W - 120}" height="${CARD_H - 120}" fill="none" stroke="${C.line}" stroke-width="2" stroke-dasharray="2 10"/>`);

  t(120, 190, 34, C.dim, `${monthLabel(p.month)} · 创作人格`, 'letter-spacing="4"');
  if (opts.author) t(960, 190, 34, C.dim, opts.author, 'text-anchor="end"');

  // 人格名
  const name = p.archetype.name;
  out.push(`<rect x="120" y="${430 - 44}" width="${Math.min(840, [...name].length * 150)}" height="44" fill="${C.yl}" opacity="0.55"/>`);
  out.push(`<text x="114" y="430" font-size="150" font-weight="700" fill="${C.text}" font-family="${SERIF}">${esc(name)}</text>`);
  wrap(p.archetype.tagline, 20, 3).forEach((line, i) => t(120, 560 + i * 64, 44, C.text, line));

  // 24 小时动作分布
  const top = 820;
  const h = 220;
  const max = Math.max(1, ...p.hours);
  t(120, top - 30, 30, C.dim, '一天里什么时候在创作', 'letter-spacing="2"');
  p.hours.forEach((v, hr) => {
    const bh = Math.max(4, Math.round((v / max) * h));
    const x = 120 + hr * 35;
    const peak = hr === p.peak_hour && v > 0;
    out.push(`<rect x="${x}" y="${top + h - bh}" width="22" height="${bh}" rx="3" fill="${peak ? C.yl : v ? C.dim : C.grid}"/>`);
  });
  [0, 6, 12, 18, 23].forEach((hr) => t(120 + hr * 35 + 11, top + h + 44, 26, C.faint, `${hr}`, 'text-anchor="middle"'));
  if (p.peak_hour !== null) t(960, top - 30, 30, C.yl, `高峰 ${p.peak_hour}:00`, 'text-anchor="end"');

  // 数字
  const cells: [string, number][] = [
    ['新项目', s.projects],
    ['产出', s.outputs],
    ['收进灵感', s.library],
    ['拆过的爆款', s.breakdowns],
    ['活跃天数', s.days],
    ['最长连续', s.streak],
  ];
  cells.forEach(([label, v], i) => {
    const x = 120 + (i % 3) * 290;
    const y = 1250 + Math.floor(i / 3) * 200;
    out.push(`<text x="${x}" y="${y}" font-size="96" font-weight="600" fill="${C.text}" font-family="'Bahnschrift','Barlow',${SANS}">${v}</text>`);
    t(x, y + 52, 30, C.dim, label);
  });

  // 平台分布
  if (p.platform_mix.length) {
    let x = 120;
    p.platform_mix.slice(0, 5).forEach((m, i) => {
      out.push(`<circle cx="${x + 10}" cy="1690" r="10" fill="${DOT[i % DOT.length]}"/>`);
      const label = `${m.label} ${m.count}`;
      t(x + 32, 1701, 32, C.text, label);
      x += 64 + [...label].length * 30;
    });
  }

  if (opts.vote) t(120, 1790, 34, C.yl, wrap(`给我投一票 → ${opts.vote}`, 26, 1)[0]);
  t(960, 1790, 28, C.faint, '创意工作台', 'text-anchor="end" letter-spacing="4"');

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${CARD_W}" height="${CARD_H}" viewBox="0 0 ${CARD_W} ${CARD_H}">${out.join('')}</svg>`;
}

export function svgDataUrl(svg: string): string {
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

/** SVG → PNG 下载（浏览器里用 canvas 栅格化）。 */
export async function downloadPng(svg: string, filename: string): Promise<void> {
  const img = new Image();
  img.decoding = 'async';
  const loaded = new Promise<void>((resolve, reject) => {
    img.onload = () => resolve();
    img.onerror = () => reject(new Error('分享图生成失败'));
  });
  img.src = svgDataUrl(svg);
  await loaded;
  const canvas = document.createElement('canvas');
  canvas.width = CARD_W;
  canvas.height = CARD_H;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('浏览器不支持导出图片');
  ctx.drawImage(img, 0, 0);
  const blob = await new Promise<Blob | null>((r) => canvas.toBlob(r, 'image/png'));
  if (!blob) throw new Error('分享图生成失败');
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

/** 配图发出去时用的文案。 */
export function shareText(p: CreatorPersona, vote?: string): string {
  const s = p.stats;
  return [
    `我的${monthLabel(p.month)}创作人格：${p.archetype.name}`,
    p.archetype.tagline,
    `${s.projects} 个新项目 · ${s.outputs} 个产出 · 活跃 ${s.days} 天`,
    vote ? `给我投一票 → ${vote}` : '',
  ]
    .filter(Boolean)
    .join('\n');
}
