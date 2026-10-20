'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import type { ReactNode } from 'react';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { CW_NAV, CW_NAV_BOTTOM, activeNavId, type CwNavItem } from './nav';
import { cwAntdTheme } from './antd-theme';
import { QuickNote } from './notes';

/** 已按调色台重做的路由；其余仍是旧页面，包在浅色容器里直到阶段 2 替换 */
export const CW_ROUTES = ['/', '/sources', '/hot', '/reports', '/dossiers', '/items', '/settings', '/library', '/notes'];

export function isCwRoute(pathname: string): boolean {
  return CW_ROUTES.some((p) => pathname === p || (p !== '/' && pathname.startsWith(`${p}/`)));
}

function Mark() {
  return (
    <svg className="cw-nav-mark" viewBox="0 0 36 36" aria-hidden="true">
      <circle cx="18" cy="18" r="16" fill="none" stroke="#333b48" />
      <circle cx="18" cy="5" r="2.4" fill="var(--cw-rd)" />
      <circle cx="29.3" cy="11.5" r="2.4" fill="var(--cw-mg)" />
      <circle cx="29.3" cy="24.5" r="2.4" fill="var(--cw-bl)" />
      <circle cx="18" cy="31" r="2.4" fill="var(--cw-cy)" />
      <circle cx="6.7" cy="24.5" r="2.4" fill="var(--cw-gr)" />
      <circle cx="6.7" cy="11.5" r="2.4" fill="var(--cw-yl)" />
    </svg>
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

  return (
    <div className="cw-app cw-shell">
      <nav className="cw-nav" aria-label="主导航">
        <Mark />
        {CW_NAV.map((group) => (
          <div key={group.id} className="cw-nav-group">
            {group.items.map((item) => (
              <NavLink key={item.id} item={item} active={active === item.id} />
            ))}
          </div>
        ))}
        <span className="cw-nav-spacer" />
        <div className="cw-nav-group">
          {CW_NAV_BOTTOM.map((item) => (
            <NavLink key={item.id} item={item} active={active === item.id} alert={item.id === 'sources' && sourcesAlert} />
          ))}
        </div>
      </nav>
      <main id="main-content" className="cw-main">
        {cw ? (
          children
        ) : (
          <div className="cw-legacy">
            {legacyBar}
            <div className="cw-legacy-body">{children}</div>
          </div>
        )}
      </main>
      <ConfigProvider theme={cwAntdTheme} locale={zhCN}>
        <QuickNote />
      </ConfigProvider>
    </div>
  );
}
