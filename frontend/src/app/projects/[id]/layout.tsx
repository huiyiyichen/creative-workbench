'use client';

/** 项目框架：所有步骤共用项目栏（设计文档 3 节）。 */

import { use, type ReactNode } from 'react';
import { CwPage } from '@/design/components';
import { ProjectProvider, ProjectShell } from '@/design/studio';

export default function ProjectLayout({ children, params }: { children: ReactNode; params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return (
    <CwPage className="cw-page-flush">
      <ProjectProvider id={Number(id)}>
        <ProjectShell>{children}</ProjectShell>
      </ProjectProvider>
    </CwPage>
  );
}
