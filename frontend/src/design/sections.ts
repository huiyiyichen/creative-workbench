/**
 * 底部入口的分页（改造方案 11.1）：
 * - 信源：信源列表、采集（3.8）、内容（原内容管理）。
 * - 设置：AI 模型与配音、生成服务、Obsidian、飞书、通知、Prompt、评分说明、系统。
 * 旧页面（/admin/*）保留路由，只把原管理后台的侧栏换成这里的分页。
 */

export interface SectionTab {
  href: string;
  label: string;
  /** 尚未上线：显示但不可点 */
  pending?: string;
}

export const SOURCES_TABS: SectionTab[] = [
  { href: '/admin/sources', label: '信源列表' },
  { href: '/sources', label: '采集' },
  { href: '/admin/contents', label: '内容' },
];

export const SETTINGS_TABS: SectionTab[] = [
  { href: '/admin/model-eval', label: 'AI 模型与配音' },
  { href: '/settings/generation', label: '生成服务' },
  { href: '/settings/obsidian', label: 'Obsidian' },
  { href: '/settings/feishu', label: '飞书', pending: '阶段 6' },
  { href: '/settings/library', label: '灵感库' },
  { href: '/settings/workbench', label: '工作台工具' },
  { href: '/settings/notify', label: '通知' },
  { href: '/admin/prompts', label: 'Prompt' },
  { href: '/settings/scoring', label: '评分说明' },
  { href: '/admin/settings', label: '系统' },
];

function under(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}

/** 当前路径属于哪组分页；不属于返回 null */
export function sectionTabsFor(pathname: string): SectionTab[] | null {
  if (SOURCES_TABS.some((t) => under(pathname, t.href))) return SOURCES_TABS;
  if (SETTINGS_TABS.some((t) => under(pathname, t.href))) return SETTINGS_TABS;
  return null;
}

export function activeTab(pathname: string, tabs: SectionTab[]): string | null {
  let best: SectionTab | null = null;
  for (const t of tabs) if (under(pathname, t.href) && (!best || t.href.length > best.href.length)) best = t;
  return best?.href ?? null;
}
