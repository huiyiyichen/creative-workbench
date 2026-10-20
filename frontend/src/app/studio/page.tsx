'use client';

/** 旧工作台已并入 /projects：保留地址做跳转（项目、内容、灵感库条目、随笔的「用于新项目」）。 */

import { useRouter } from 'next/navigation';
import { useEffect } from 'react';
import { studioRedirect } from '@/lib/studio-redirect';

export default function StudioRedirect() {
  const router = useRouter();
  useEffect(() => {
    router.replace(studioRedirect(window.location.search));
  }, [router]);
  return null;
}
