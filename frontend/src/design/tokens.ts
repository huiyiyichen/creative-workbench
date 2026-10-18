/**
 * 方向 A「调色台」设计 token（改造方案 12.1）。
 *
 * 唯一来源：`tokens.css` 用同样的值声明 CSS 变量，Tailwind（`@theme` 的 cw-* 颜色）
 * 和 antd `ConfigProvider` 都从这里取值；`tokens.test.ts` 校验两边一致。
 */

export const color = {
  base: '#15181d',
  panel: '#1a1e25',
  raise: '#222731',
  grat: '#262c36',
  line: '#333b48',
  text: '#e8eaed',
  dim: '#8d96a3',
  faint: '#5e6774',
  navBg: '#12151a',
  deep: '#0f1216',
  yl: '#e3cc4b',
  mg: '#df5bd5',
  bl: '#6f8bff',
  cy: '#4fd2e2',
  gr: '#6ccf68',
  rd: '#ff6159',
  wh: '#f4f5f7',
  paper: '#f6f3ec',
  ink: '#1d1f23',
} as const;

/** 内容形态色标：全站同一种形态用同一种颜色（12.1） */
export const mediaColor = {
  article: color.yl,
  video: color.mg,
  image: color.bl,
  prompt: color.cy,
  repo: color.gr,
  list: color.rd,
  project: color.wh,
  note: color.dim,
} as const;

export type MediaKind = keyof typeof mediaColor;

/** 选题结论标记 */
export const verdictColor = {
  do: color.gr,
  watch: color.yl,
  skip: color.faint,
} as const;

export const font = {
  sans: 'var(--font-noto-sans-sc), "Noto Sans SC", "Microsoft YaHei UI", sans-serif',
  num: '"Bahnschrift", var(--font-barlow-sc), "Segoe UI", sans-serif',
  serif: 'var(--font-display), "Noto Serif SC", "Songti SC", serif',
} as const;

export const radius = { sm: 6, md: 8, lg: 12 } as const;

/** 桌面两档：≥1280 完整布局；1024–1279 侧栏收起（12.4） */
export const breakpoint = { full: 1280, compact: 1024 } as const;
