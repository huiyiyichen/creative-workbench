'use client';

/** 侧栏「创作」：有上次没写完的项目就回到原来那一步，没有才新建空白项目。 */

import { useRouter } from 'next/navigation';
import { useEffect, useRef } from 'react';
import { CwPage } from '@/design/components';
import { projectsApi } from '@/lib/api/_projects';
import { forgetProject, lastProject } from '@/lib/last-project';

export default function CreatePage() {
  const router = useRouter();
  const started = useRef(false);
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    const last = lastProject();
    if (!last) {
      router.replace('/projects/new');
      return;
    }
    projectsApi
      .get(last.id)
      .then((p) => {
        if (p.archived) throw new Error('archived');
        router.replace(last.path);
      })
      .catch(() => {
        forgetProject();
        router.replace('/projects/new');
      });
  }, [router]);
  return (
    <CwPage>
      <p className="cw-muted">正在回到上次的创作…</p>
    </CwPage>
  );
}
