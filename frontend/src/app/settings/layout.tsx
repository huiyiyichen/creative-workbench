'use client';

import type { ReactNode } from 'react';
import { CwPage, TopBar } from '@/design/components';
import { SectionTabs } from '@/design/SectionTabs';

export default function SettingsLayout({ children }: { children: ReactNode }) {
  return (
    <CwPage>
      <TopBar title="设置" />
      <SectionTabs label="设置分页" />
      {children}
    </CwPage>
  );
}
