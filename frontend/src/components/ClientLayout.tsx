'use client';

import React from 'react';
import { usePathname } from 'next/navigation';
import NotificationBell from '@/components/NotificationBell';
import ProductionStatus from '@/components/ProductionStatus';
import AppShell from '@/design/AppShell';
import { useSourcesAlert } from '@/design/useSourcesAlert';
import { AppProvider, useAuthContext, useAppContext } from '@/providers/AppProvider';
import type { PrefetchData } from '@/lib/server-prefetch';

// Backward compat: 旧页面从 @/components/ClientLayout 导入 useAppContext
export { useAppContext };

const ADMIN_PATH_PREFIX = '/admin';

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
  const pathname = usePathname() || '/';
  const { currentUser } = useAuthContext();
  const sourcesAlert = useSourcesAlert();
  const isAdminPath = pathname === ADMIN_PATH_PREFIX || pathname.startsWith(`${ADMIN_PATH_PREFIX}/`);

  const legacyBar = isAdminPath ? null : (
    <div className="flex h-12 shrink-0 items-center justify-end border-b border-gray-100 bg-white px-6">
      <ProductionStatus />
      {currentUser && <NotificationBell />}
    </div>
  );

  return (
    <AppShell legacyBar={legacyBar} sourcesAlert={sourcesAlert}>
      {children}
    </AppShell>
  );
}
