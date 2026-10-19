'use client';

/** 条目详情独立页（5.6）：与抽屉共用 ItemDetailView。 */

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { ArrowLeft } from 'lucide-react';
import { CwPage } from '@/design/components';
import { ItemDetailView } from '@/design/discover';

export default function ItemPage() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  return (
    <CwPage className="cw-item-page">
      <Link href="/" className="cw-btn" data-variant="ghost">
        <ArrowLeft size={15} />
        今日
      </Link>
      {Number.isFinite(id) && id > 0 ? (
        <div style={{ maxWidth: 860 }}>
          <ItemDetailView id={id} />
        </div>
      ) : (
        <div className="cw-error">条目编号不对</div>
      )}
    </CwPage>
  );
}
