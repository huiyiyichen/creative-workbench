'use client';

/**
 * 原管理后台的保留页面（11.2）：信源列表、内容、AI 模型、Prompt、系统。
 * 管理后台整体取消：不再有侧栏和概览，顶部改为「信源」或「设置」的分页；页面跟随主题（.cw-legacy-area 换调色板）。
 */

import React from 'react';
import { usePathname } from 'next/navigation';
import { SettingsShell, SourcesTopBar } from '@/design/SectionTabs';
import { CwAntd, CwPage } from '@/design/components';
import { SOURCES_TABS, sectionTabsFor } from '@/design/sections';

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() || '';
  const tabs = sectionTabsFor(pathname);
  if (tabs !== SOURCES_TABS) {
    return (
      <CwAntd>
        <div className="h-full overflow-auto">
          <SettingsShell legacy>{children}</SettingsShell>
        </div>
      </CwAntd>
    );
  }
  // 与 /sources（采集）同一个页面壳和顶栏：主题、内边距、分段导航位置三页一致
  return (
    <div className="cw-main-scroll">
      <CwPage className="cw-sources-page">
        <SourcesTopBar />
        <div className="cw-legacy-area cw-sources-body">{children}</div>
      </CwPage>
    </div>
  );
}
