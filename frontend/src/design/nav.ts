import {
  Bookmark,
  FileStack,
  Flame,
  FolderKanban,
  ListChecks,
  Wallet,
  Newspaper,
  SquarePen,
  RadioTower,
  Settings,
  Sun,
  Waypoints,
  type LucideIcon,
} from 'lucide-react';

/**
 * 主导航（改造方案 11.1）。
 *
 * 阶段 0 只先换导航结构：尚未重做的分区指向现有页面（11.2 的去向），
 * 还没有页面的入口（作品）显示为不可用，阶段 5 上线后接上。
 */
export interface CwNavItem {
  id: string;
  label: string;
  href: string;
  icon: LucideIcon;
  /** 这些路径前缀也算当前入口 */
  match?: string[];
  /** 尚未上线的入口：显示但不可点击 */
  pending?: string;
}

export interface CwNavGroup {
  id: string;
  items: CwNavItem[];
}

export const CW_NAV: CwNavGroup[] = [
  {
    id: 'discover',
    items: [
      { id: 'today', label: '今日', href: '/', icon: Sun, match: ['/items'] },
      { id: 'hot', label: '热点', href: '/hot', icon: Flame },
      { id: 'reports', label: '报告', href: '/reports', icon: Newspaper, match: ['/daily', '/weekly', '/monthly'] },
      { id: 'topics', label: '专题', href: '/dossiers', icon: Waypoints },
    ],
  },
  {
    id: 'inspire',
    items: [{ id: 'library', label: '灵感库', href: '/library', icon: Bookmark, match: ['/notes', '/favorites'] }],
  },
  {
    id: 'create',
    items: [
      // 直接开始创作：新建空白项目并进入「选题与创意」，不经过项目看板（用户 2026-10-21 反馈）
      { id: 'new', label: '创作', href: '/create', icon: SquarePen, match: ['/projects/new'] },
      { id: 'projects', label: '项目', href: '/projects', icon: FolderKanban, match: ['/studio'] },
    ],
  },
  {
    id: 'output',
    items: [
      { id: 'works', label: '作品', href: '/works', icon: FileStack },
      { id: 'tasks', label: '任务', href: '/tasks', icon: ListChecks, match: ['/runs', '/stats/jobs'] },
      { id: 'costs', label: '花费', href: '/costs', icon: Wallet },
    ],
  },
];

export const CW_NAV_BOTTOM: CwNavItem[] = [
  { id: 'sources', label: '信源', href: '/sources', icon: RadioTower, match: ['/admin/sources', '/admin/contents'] },
  {
    id: 'settings',
    label: '设置',
    href: '/admin/model-eval',
    icon: Settings,
    match: ['/settings', '/admin/model-eval', '/admin/prompts', '/admin/settings'],
  },
];

function matches(pathname: string, prefix: string): boolean {
  if (prefix === '/') return pathname === '/';
  return pathname === prefix || pathname.startsWith(`${prefix}/`);
}

/** 当前路径对应的导航 id；更具体（更长）的前缀优先 */
export function activeNavId(pathname: string): string | null {
  // 项目内页（选题 / 文稿 / 产出）就是创作现场：亮「创作」，「项目」只代表看板
  if (/^\/projects\/(new|\d+)(\/|$)/.test(pathname) || /^\/create(\/|$)/.test(pathname)) return 'new';
  const all = [...CW_NAV.flatMap((g) => g.items), ...CW_NAV_BOTTOM];
  let best: { id: string; len: number } | null = null;
  for (const item of all) {
    if (item.pending) continue;
    for (const prefix of [item.href, ...(item.match ?? [])]) {
      if (matches(pathname, prefix) && (!best || prefix.length > best.len)) {
        best = { id: item.id, len: prefix.length };
      }
    }
  }
  return best?.id ?? null;
}
