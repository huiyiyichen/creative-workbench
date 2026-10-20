'use client';

/** 第三步：产出（设计文档 6 节）——左侧产出物列表，右侧工作区。 */

import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { Dropdown, message } from 'antd';
import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { Button } from '@/design/components';
import { OUTPUT_LABEL, OUTPUT_STATUS, apiError, useProject } from '@/design/studio';
import { projectsApi, type OutputKind, type OutputView } from '@/lib/api/_projects';
import { OutputsContext as Ctx } from './_ctx';

const KINDS: OutputKind[] = ['xhs', 'zhihu', 'wechat', 'video', 'prompt_bundle', 'mv'];
const RENDER: OutputKind[] = ['video', 'mv', 'prompt_bundle'];


export default function OutputsLayout({ children }: { children: ReactNode }) {
  const { project } = useProject();
  const params = useParams<{ outputId?: string }>();
  const router = useRouter();
  const [items, setItems] = useState<OutputView[]>([]);
  const pid = project?.id;
  const reload = useCallback(async () => {
    if (!pid) return;
    try {
      setItems((await projectsApi.outputs(pid)).items);
    } catch (err) {
      message.error(apiError(err, '产出物加载失败'));
    }
  }, [pid]);
  useEffect(() => {
    void reload();
  }, [reload]);
  if (!project) return null;
  const finalized = Boolean(project.finalized_version);
  const create = async (kind: OutputKind) => {
    try {
      const o = await projectsApi.createOutput(project.id, kind);
      await reload();
      router.push(`/projects/${project.id}/outputs/${o.id}`);
    } catch (err) {
      message.error(apiError(err));
    }
  };
  const current = params.outputId ? Number(params.outputId) : null;
  return (
    <Ctx.Provider value={{ items, reload }}>
      <div className="cw-outputs">
        <aside className="cw-outlist">
          <Dropdown
            trigger={['click']}
            menu={{
              items: KINDS.map((k) => ({
                key: k,
                label: OUTPUT_LABEL[k] + (RENDER.includes(k) && !finalized ? '（定稿后可建）' : ''),
                disabled: RENDER.includes(k) && !finalized,
              })),
              onClick: ({ key }) => create(key as OutputKind),
            }}
          >
            <Button variant="primary" style={{ width: '100%' }}>
              + 新建产出 ▾
            </Button>
          </Dropdown>
          {!finalized ? <p className="cw-muted" style={{ fontSize: 12 }}>未定稿时只能先建平台版本草稿；视频、MV、提示词包定稿后可制作。</p> : null}
          <ul>
            {items.map((o) => {
              const [label, c] = OUTPUT_STATUS[o.status] || [o.status, 'var(--cw-dim)'];
              return (
                <li key={o.id}>
                  <Link href={`/projects/${project.id}/outputs/${o.id}`} className="cw-outcard" aria-current={current === o.id ? 'page' : undefined}>
                    <b>{o.title}</b>
                    <span className="cw-row">
                      <span className="cw-outstatus" style={{ color: c }}>
                        {label}
                      </span>
                      {o.based_on_version ? <span className="cw-num cw-muted">v{o.based_on_version}</span> : null}
                      {o.content?.body ? <span className="cw-num cw-muted">{String(o.content.body).length} 字</span> : null}
                    </span>
                    {o.stale ? <small className="cw-outstale">文稿已更新到 v{o.latest_finalized}</small> : null}
                  </Link>
                </li>
              );
            })}
          </ul>
        </aside>
        <section className="cw-outwork">{children}</section>
      </div>
    </Ctx.Provider>
  );
}
