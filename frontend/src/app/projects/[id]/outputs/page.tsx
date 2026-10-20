'use client';

import Link from 'next/link';
import { useProject } from '@/design/studio';
import { useOutputs } from './_ctx';

export default function OutputsIndex() {
  const { project } = useProject();
  const { items } = useOutputs();
  if (!project) return null;
  if (!project.finalized_version) {
    return (
      <div className="cw-outempty">
        <h3>定稿后可制作</h3>
        <p className="cw-muted">讲解视频、音乐 MV、视频提示词包都基于定稿文案；平台版本可以先建草稿。</p>
        <Link className="cw-btn" data-variant="primary" href={`/projects/${project.id}/draft`}>
          去定稿
        </Link>
      </div>
    );
  }
  return (
    <div className="cw-outempty">
      <h3>{items.length ? '从左侧选一个产出物' : '还没有产出物'}</h3>
      <p className="cw-muted">用「新建产出」做小红书 / 知乎 / 公众号版本、讲解视频、视频提示词包或音乐 MV。</p>
    </div>
  );
}
