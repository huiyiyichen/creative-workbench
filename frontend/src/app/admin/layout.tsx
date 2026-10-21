'use client';

/**
 * 原管理后台的保留页面（11.2）：信源列表、内容、AI 模型、Prompt、系统。
 * 管理后台整体取消：不再有侧栏和概览，顶部改为「信源」或「设置」的分页；页面跟随主题（.cw-legacy-area 换调色板）。
 */

import React from 'react';
import { usePathname } from 'next/navigation';
import { SectionTabs, SettingsShell } from '@/design/SectionTabs';
import { SOURCES_TABS, sectionTabsFor } from '@/design/sections';

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() || '';
  const tabs = sectionTabsFor(pathname);
  const title = tabs === SOURCES_TABS ? '信源' : '设置';
  if (tabs !== SOURCES_TABS) {
    return (
      <div className="h-full overflow-auto">
        <SettingsShell legacy>{children}</SettingsShell>
      </div>
    );
  }
  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="cw-app cw-legacy-head">
        <header className="cw-topbar">
          <h1>{title}</h1>
          <span className="cw-grow" />
        </header>
        <SectionTabs label={`${title}分页`} />
      </div>
      <div className="cw-legacy-area min-h-0 flex-1 overflow-auto bg-page">{children}</div>
    </div>
  );
}
