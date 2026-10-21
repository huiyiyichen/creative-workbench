'use client';
import type React from 'react';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { activeTab, sectionTabsFor, type SectionTab } from './sections';

export function SectionTabs({ tabs, label }: { tabs?: SectionTab[]; label?: string }) {
  const pathname = usePathname() || '/';
  const list = tabs ?? sectionTabsFor(pathname);
  if (!list) return null;
  const current = activeTab(pathname, list);
  return (
    <nav className="cw-tabs" aria-label={label ?? '分页'}>
      {list.map((t) =>
        t.pending ? (
          <span key={t.href} aria-disabled="true" title={`${t.pending}上线`} style={{ padding: '8px 14px', color: 'var(--cw-faint)', fontSize: 14 }}>
            {t.label}
          </span>
        ) : (
          <Link key={t.href} href={t.href} aria-current={current === t.href ? 'page' : undefined}>
            {t.label}
          </Link>
        ),
      )}
    </nav>
  );
}

/**
 * 设置外壳（评审 #3 2.6）：全站 TopBar + 左侧 200px 竖导航，12 个分页不再横排挤满。
 * /settings/* 与 /admin/*（模型、Prompt、系统）共用同一个外壳。
 */
export function SettingsShell({ children, legacy }: { children: React.ReactNode; legacy?: boolean }) {
  const pathname = usePathname() || '/';
  const list = sectionTabsFor(pathname) ?? [];
  const current = activeTab(pathname, list);
  return (
    <div className="cw-settings">
      <header className="cw-topbar cw-settings-top">
        <h1>设置</h1>
      </header>
      <div className="cw-settings-grid">
        <nav className="cw-sidetabs" aria-label="设置分页">
          {list.map((t) => (
            <Link key={t.href} href={t.href} aria-current={current === t.href ? 'page' : undefined}>
              {t.label}
            </Link>
          ))}
        </nav>
        <div className={legacy ? 'cw-settings-body cw-legacy-area' : 'cw-settings-body'}>{children}</div>
      </div>
    </div>
  );
}
