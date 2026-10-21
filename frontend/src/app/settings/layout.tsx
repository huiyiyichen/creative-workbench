'use client';

import type { ReactNode } from 'react';
import { CwPage } from '@/design/components';
import { SettingsShell } from '@/design/SectionTabs';

export default function SettingsLayout({ children }: { children: ReactNode }) {
  return (
    <CwPage className="cw-page-flush">
      <SettingsShell>{children}</SettingsShell>
    </CwPage>
  );
}
