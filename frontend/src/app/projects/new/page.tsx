'use client';

/** /projects/new?source=content:123 —— 带来源新建项目后进入第一步。 */

import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useEffect, useRef, useState } from 'react';
import { CwPage } from '@/design/components';
import { apiError } from '@/design/studio';
import { projectsApi } from '@/lib/api/_projects';

function Creator() {
  const router = useRouter();
  const params = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  const started = useRef(false);
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    const sources = (params.get('source') || '').split(',').filter((s) => /^(content|library):\d+$/.test(s));
    projectsApi
      .create({ theme: params.get('theme') || '', sources })
      .then((p) => router.replace(`/projects/${p.id}/idea`))
      .catch((err) => setError(apiError(err, '新建失败')));
  }, [params, router]);
  return error ? <div className="cw-error">{error}</div> : <div className="cw-empty">正在新建项目…</div>;
}

export default function NewProjectPage() {
  return (
    <CwPage>
      <Suspense fallback={null}>
        <Creator />
      </Suspense>
    </CwPage>
  );
}
