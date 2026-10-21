'use client';

import React from 'react';
import AppShell from '@/design/AppShell';
import { useSourcesAlert } from '@/design/useSourcesAlert';
import { AppProvider, useAppContext } from '@/providers/AppProvider';
import type { PrefetchData } from '@/lib/server-prefetch';

// Backward compat: 旧页面从 @/components/ClientLayout 导入 useAppContext
export { useAppContext };


/**
 * 根布局壳：调色台主导航（改造方案 11.1）+ 页面区。
 *
 * 已重做的页面（见 design/AppShell 的 CW_ROUTES）直接用暗色；旧页面在阶段 2
 * 逐个替换前包在浅色容器里，顶部保留通知与制作状态。
 */
export default function ClientLayout({
  children,
  initialData,
}: {
  children: React.ReactNode;
  initialData: PrefetchData;
}) {
  return (
    <AppProvider initialData={initialData}>
      <LayoutChrome>{children}</LayoutChrome>
    </AppProvider>
  );
}

function LayoutChrome({ children }: { children: React.ReactNode }) {
  const sourcesAlert = useSourcesAlert();
  // 旧页顶条只有一个铃铛，和导航底部的通知中心重复，去掉（评审 #3 2.2）
  return (
    <AppShell sourcesAlert={sourcesAlert}>
      {children}
    </AppShell>
  );
}
