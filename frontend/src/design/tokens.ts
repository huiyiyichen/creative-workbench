/**
 * 方向 A「调色台」设计 token（改造方案 12.1）。
 *
 * 唯一来源：`tokens.css` 用同样的值声明 CSS 变量，Tailwind（`@theme` 的 cw-* 颜色）
 * 和 antd `ConfigProvider` 都从这里取值；`tokens.test.ts` 校验两边一致。
 */

export type CwTheme = 'dark' | 'light';

/** 暗色主题（默认）。文稿纸面在暗色里是一张深灰纸，免得和外壳对比过大 */
export const darkColor = {
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
  onWh: '#14171c',
  paperBg: '#1e2229',
  paperInk: '#d3d7dc',
  paperSub: '#8d96a3',
  paperLine: '#30363f',
  paperPh: '#5e6774',
} as const;

/** 亮色主题：强调色压暗一档，保证浅底上可读 */
export const lightColor = {
  base: '#f2f3f0',
  panel: '#fbfbf9',
  raise: '#e9ebe6',
  grat: '#e2e4df',
  line: '#cfd3cb',
  text: '#1f232a',
  dim: '#5d6570',
  faint: '#8f969f',
  navBg: '#e9ebe6',
  deep: '#dfe2dc',
  yl: '#a8870a',
  mg: '#b03a9f',
  bl: '#3d5ad6',
  cy: '#0e8fa3',
  gr: '#2e8c37',
  rd: '#d03a31',
  wh: '#1f232a',
  paper: '#f6f3ec',
  ink: '#1d1f23',
  onWh: '#f6f7f4',
  paperBg: '#fdfcf8',
  paperInk: '#24272c',
  paperSub: '#5d6570',
  paperLine: '#dedfd8',
  paperPh: '#a0a59f',
} satisfies Record<keyof typeof darkColor, string>;

export const palettes: Record<CwTheme, Record<keyof typeof darkColor, string>> = { dark: darkColor, light: lightColor };

type ColorName = keyof typeof darkColor;
const kebab = (name: string) => name.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`);

/**
 * 页面里内联用的颜色：CSS 变量引用，随主题切换自动变。
 * 需要真实色值的地方（antd token）用 palettes[theme]。
 */
export const color = Object.fromEntries(
  (Object.keys(darkColor) as ColorName[]).map((k) => [k, `var(--cw-${kebab(k)})`]),
) as { readonly [K in ColorName]: string };

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
