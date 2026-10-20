'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useCallback, useState, type ReactNode } from 'react';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { CW_NAV, CW_NAV_BOTTOM, activeNavId, type CwNavItem } from './nav';
import { Moon, Search, Sun } from 'lucide-react';
import { cwAntdThemeFor } from './antd-theme';
import { useCwTheme } from './theme';
import { QuickNote } from './notes';
import { TaskDrawer, useTaskCount } from './tasks';
import { CommandPalette, OPEN_EVENT } from './command';
import { NotificationDrawer, NotifyButton, useUnreadCount } from './notifications';

/** 已按调色台重做的路由；其余旧页面（管理页、日报 / 周刊 / 月刊）包在 .cw-legacy 里，调色板换成 --cw-* 变量跟随主题 */
export const CW_ROUTES = ['/', '/sources', '/hot', '/reports', '/dossiers', '/items', '/settings', '/library', '/notes', '/runs', '/projects', '/tasks', '/works', '/search'];

export function isCwRoute(pathname: string): boolean {
  return CW_ROUTES.some((p) => pathname === p || (p !== '/' && pathname.startsWith(`${p}/`)));
}

function Mark() {
  return (
    <svg className="cw-nav-mark" viewBox="0 0 36 36" aria-hidden="true">
      <circle cx="18" cy="18" r="16" fill="none" stroke="var(--cw-line)" />
      <circle cx="18" cy="5" r="2.4" fill="var(--cw-rd)" />
      <circle cx="29.3" cy="11.5" r="2.4" fill="var(--cw-mg)" />
      <circle cx="29.3" cy="24.5" r="2.4" fill="var(--cw-bl)" />
      <circle cx="18" cy="31" r="2.4" fill="var(--cw-cy)" />
      <circle cx="6.7" cy="24.5" r="2.4" fill="var(--cw-gr)" />
      <circle cx="6.7" cy="11.5" r="2.4" fill="var(--cw-yl)" />
    </svg>
  );
}

function ThemeToggle() {
  const [mode, setMode] = useCwTheme();
  const next = mode === 'light' ? 'dark' : 'light';
  const label = next === 'light' ? '切到亮色' : '切到暗色';
  const Icon = next === 'light' ? Sun : Moon;
  return (
    <button type="button" className="cw-nav-item cw-theme-toggle" onClick={() => setMode(next)} title={label} aria-label={label}>
      <Icon aria-hidden="true" />
    </button>
  );
}

/** 导航「任务」：显示进行中的数量，点开全局抽屉 */
function TasksNav({ item, active, onOpen }: { item: CwNavItem; active: boolean; onOpen: () => void }) {
  const Icon = item.icon;
  const count = useTaskCount();
  return (
    <button type="button" className="cw-nav-item" aria-current={active ? 'page' : undefined} title={item.label} onClick={onOpen}>
      <Icon aria-hidden="true" />
      <span className="cw-nav-label">{item.label}</span>
      {count ? <i className="cw-nav-count" aria-label={`${count} 个进行中`}>{count > 99 ? '99+' : count}</i> : null}
    </button>
  );
}

function NavLink({ item, active, alert }: { item: CwNavItem; active: boolean; alert?: boolean }) {
  const Icon = item.icon;
  if (item.pending) {
    return (
      <span className="cw-nav-item" aria-disabled="true" title={`${item.label}（${item.pending}）`}>
        <Icon aria-hidden="true" />
        <span className="cw-nav-label">{item.label}</span>
      </span>
    );
  }
  return (
    <Link href={item.href} className="cw-nav-item" aria-current={active ? 'page' : undefined} title={item.label}>
      <Icon aria-hidden="true" />
      <span className="cw-nav-label">{item.label}</span>
      {alert ? <i className="cw-nav-badge" aria-label="有信源需要处理" /> : null}
    </Link>
  );
}

export default function AppShell({
  children,
  legacyBar,
  sourcesAlert = false,
}: {
  children: ReactNode;
  /** 旧页面顶部的通知 / 制作状态条，阶段 2 重做后移除 */
  legacyBar?: ReactNode;
  sourcesAlert?: boolean;
}) {
  const pathname = usePathname() || '/';
  const active = activeNavId(pathname);
  const cw = isCwRoute(pathname);
  const [mode, setMode] = useCwTheme();
  const [tasksOpen, setTasksOpen] = useState(false);
  const [notifyOpen, setNotifyOpen] = useState(false);
  const [unread, reloadUnread] = useUnreadCount();
  const toggleTheme = useCallback(() => setMode(mode === 'light' ? 'dark' : 'light'), [mode, setMode]);
  const openTasks = useCallback(() => setTasksOpen(true), []);

  return (
    <div className="cw-app cw-shell">
      <nav className="cw-nav" aria-label="主导航">
        <Mark />
        {CW_NAV.map((group) => (
          <div key={group.id} className="cw-nav-group">
            {group.items.map((item) =>
              item.id === 'tasks' ? (
                <TasksNav key={item.id} item={item} active={active === item.id} onOpen={() => setTasksOpen(true)} />
              ) : (
                <NavLink key={item.id} item={item} active={active === item.id} />
              ),
            )}
          </div>
        ))}
        <span className="cw-nav-spacer" />
        <div className="cw-nav-group">
          {CW_NAV_BOTTOM.map((item) => (
            <NavLink key={item.id} item={item} active={active === item.id} alert={item.id === 'sources' && sourcesAlert} />
          ))}
        </div>
        {/* 跳转、主题是工具按钮：并排成一行小图标，不占主导航的位置（样张底部只有设置） */}
        <div className="cw-nav-mini">
          <NotifyButton count={unread} onOpen={() => setNotifyOpen(true)} />
          <button type="button" className="cw-nav-item" title="搜索与跳转（Ctrl K）" aria-label="搜索与跳转（Ctrl K）" onClick={() => window.dispatchEvent(new Event(OPEN_EVENT))}>
            <Search aria-hidden="true" />
          </button>
          <ThemeToggle />
        </div>
      </nav>
      <main id="main-content" className="cw-main">
        {cw ? (
          children
        ) : (
          <ConfigProvider theme={cwAntdThemeFor(mode)} locale={zhCN}>
            <div className="cw-legacy">
              {legacyBar}
              <div className="cw-legacy-body">{children}</div>
            </div>
          </ConfigProvider>
        )}
      </main>
      <ConfigProvider theme={cwAntdThemeFor(mode)} locale={zhCN}>
        <QuickNote />
        <TaskDrawer open={tasksOpen} onClose={() => setTasksOpen(false)} />
        <NotificationDrawer open={notifyOpen} onClose={() => setNotifyOpen(false)} onChanged={reloadUnread} />
        <CommandPalette onToggleTheme={toggleTheme} onOpenTasks={openTasks} />
      </ConfigProvider>
    </div>
  );
}
