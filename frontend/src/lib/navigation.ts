import {
  BarChart3,
  Bookmark,
  CalendarDays,
  ClipboardList,
  GitBranch,
  Lightbulb,
  PenLine,
  Newspaper,
  RadioTower,
  Search,
  ShieldCheck,
  Star,
  TrendingUp,
  type LucideIcon,
} from 'lucide-react';
import type { AuthUser } from '@/types';

export type NavAccess = 'public' | 'user' | 'admin';

export interface NavItem {
  id: string;
  label: string;
  href: string;
  icon: LucideIcon;
  access: NavAccess;
  countKey?: 'topics' | 'todayPicks' | 'favorites' | 'sources';
  /** 功能模块开关 key。若设置且对应 flag !== true，菜单项不渲染、路由被守卫拦截 */
  feature?: string;
}

export interface NavSpace {
  id: string;
  label: string;
  items: NavItem[];
}

export const NAV_SPACES: NavSpace[] = [
  {
    id: 'discover',
    label: '发现',
    items: [
      { id: 'trending', label: '趋势雷达', href: '/trending', icon: Search, access: 'public' },
      { id: 'trends', label: '趋势追踪', href: '/trends', icon: TrendingUp, access: 'public' },
    ],
  },
  {
    id: 'today',
    label: '今日',
    items: [
      { id: 'today', label: '今日选题', href: '/', icon: Lightbulb, access: 'public', countKey: 'topics' },
      { id: 'picks', label: '当日精选', href: '/today-picks', icon: Star, access: 'public', countKey: 'todayPicks' },
    ],
  },
  {
    id: 'review',
    label: '复盘',
    items: [
      { id: 'daily', label: '日报', href: '/daily', icon: Newspaper, access: 'public' },
      { id: 'weekly', label: '周刊', href: '/weekly', icon: ClipboardList, access: 'public' },
      { id: 'monthly', label: '月刊', href: '/monthly', icon: CalendarDays, access: 'public' },
      { id: 'stats', label: '数据统计', href: '/stats', icon: BarChart3, access: 'public' },
    ],
  },
  {
    id: 'create',
    label: '创作',
    items: [
      { id: 'studio', label: '创作工作台', href: '/studio', icon: PenLine, access: 'public' },
      { id: 'my-sources', label: '我的信源', href: '/sources/me', icon: RadioTower, access: 'public', countKey: 'sources' },
      { id: 'favorites', label: '收藏夹', href: '/favorites', icon: Bookmark, access: 'public', countKey: 'favorites' },
      { id: 'algorithm', label: '算法流程', href: '/algorithm', icon: GitBranch, access: 'public' },
    ],
  },
  {
    id: 'manage',
    label: '管理',
    items: [
      { id: 'admin-console', label: '管理后台', href: '/admin', icon: ShieldCheck, access: 'admin' },
    ],
  },
];

// admin 子路径虽被 /admin 前缀匹配覆盖，但显式列出保持安全冗余
const EXTRA_ADMIN_ONLY_PATHS = [
  '/admin/contents',
  '/admin/mother-topics',
  '/admin/updates',
  '/admin/sources',
  '/admin/model-eval',
  '/admin/feedback',
  '/admin/settings',
];

const PUBLIC_PATHS = ['/'];

function uniquePaths(paths: string[]): string[] {
  return Array.from(new Set(paths));
}

function navPathsForAccess(access: NavAccess): string[] {
  return NAV_SPACES.flatMap((space) => space.items)
    .filter((item) => item.access === access)
    .map((item) => item.href);
}

export const USER_ONLY_PATHS = uniquePaths(navPathsForAccess('user'));
export const ADMIN_ONLY_PATHS = uniquePaths([...navPathsForAccess('admin'), ...EXTRA_ADMIN_ONLY_PATHS]);

export function isAdmin(user: AuthUser | null): boolean {
  return user?.role === 'admin';
}

/** 检查某 feature 是否已启用。enabledFeatures 未加载时默认视为关（安全侧） */
function isFeatureEnabled(feature: string | undefined, enabledFeatures?: Record<string, boolean>): boolean {
  if (!feature) return true;  // 无 feature 关联 → 不受开关约束
  return Boolean(enabledFeatures?.[feature]);
}

export function canAccessNavItem(item: NavItem, user: AuthUser | null, enabledFeatures?: Record<string, boolean>): boolean {
  if (!isFeatureEnabled(item.feature, enabledFeatures)) return false;
  if (item.access === 'public') return true;
  if (item.access === 'admin') return isAdmin(user);
  return Boolean(user);
}

export function visibleNavSpaces(user: AuthUser | null, enabledFeatures?: Record<string, boolean>): NavSpace[] {
  return NAV_SPACES
    .map((space) => ({
      ...space,
      items: space.items.filter((item) => canAccessNavItem(item, user, enabledFeatures)),
    }))
    .filter((space) => space.items.length > 0);
}

function matchesPath(pathname: string, href: string): boolean {
  if (href === '/') return pathname === '/';
  return pathname === href || pathname.startsWith(`${href}/`);
}

/** 找到匹配当前路径的 NavItem（用于 feature 守卫） */
function navItemForPath(pathname: string): NavItem | undefined {
  for (const space of NAV_SPACES) {
    for (const item of space.items) {
      if (matchesPath(pathname, item.href)) return item;
    }
  }
  return undefined;
}

export function requiredAccessForPath(pathname: string, enabledFeatures?: Record<string, boolean>): NavAccess {
  // feature 关闭的路径直接返回 'user'（让守卫把已登录用户踢回首页，未登录去登录页）
  // 这里返回 user 是为了让 canAccessPath 的 fallthrough 逻辑处理，真正的拦截在 canAccessPath
  if (PUBLIC_PATHS.some((href) => matchesPath(pathname, href))) return 'public';
  if (ADMIN_ONLY_PATHS.some((href) => matchesPath(pathname, href))) return 'admin';
  if (USER_ONLY_PATHS.some((href) => matchesPath(pathname, href))) return 'user';
  return 'public';
}

export function canAccessPath(pathname: string, user: AuthUser | null, enabledFeatures?: Record<string, boolean>): boolean {
  // feature 守卫：路径关联了未启用的 feature → 不可访问
  const item = navItemForPath(pathname);
  if (item && !isFeatureEnabled(item.feature, enabledFeatures)) return false;

  const access = requiredAccessForPath(pathname, enabledFeatures);
  if (access === 'public') return true;
  if (access === 'admin') return isAdmin(user);
  return Boolean(user);
}
