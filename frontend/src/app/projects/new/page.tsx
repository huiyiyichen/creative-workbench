'use client';

/** 从别处「用于新项目」：/projects/new?source=content:1&source=library:2&source=note:3&theme=… → 新建后进入选题与创意。 */

import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useEffect, useRef, useState } from 'react';
import { CwPage } from '@/design/components';
import { apiError } from '@/design/studio';
import { projectsApi } from '@/lib/api/_projects';

function NewProject() {
  const params = useSearchParams();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const started = useRef(false);
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    const sources = params
      .getAll('source')
      .flatMap((v) => v.split(','))
      .filter((s) => /^(content|library|note):\d+$/.test(s));
    projectsApi
      .create({ theme: params.get('theme') || '', sources, intent: params.get('intent') || undefined })
      .then((p) => router.replace(`/projects/${p.id}/idea`))
      .catch((err) => setError(apiError(err, '新建项目失败')));
  }, [params, router]);
  return <CwPage>{error ? <div className="cw-error">{error}</div> : <p className="cw-muted">正在新建项目…</p>}</CwPage>;
}

export default function NewProjectPage() {
  return (
    <Suspense fallback={null}>
      <NewProject />
    </Suspense>
  );
}
