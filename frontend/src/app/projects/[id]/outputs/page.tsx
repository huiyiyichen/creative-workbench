'use client';

/** 产出总览：每种产出一格（已有的显示状态，没有的可以直接新建），像一排通道。 */

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Plus } from 'lucide-react';
import { useState, type CSSProperties } from 'react';
import { toast } from '@/design/feedback';
import { EmptyInstrument, StatusLamp, type LampTone } from '@/design/instrument';
import { SignalArt, kindColor } from '@/design/signal-art';
import { OUTPUT_LABEL, OUTPUT_STATUS, apiError, useProject } from '@/design/studio';
import { projectsApi, type OutputKind } from '@/lib/api/_projects';
import { useOutputs } from './_ctx';

const KINDS: { kind: OutputKind; desc: string; needsFinal: boolean }[] = [
  { kind: 'xhs', desc: '标题、正文、标签、封面文案', needsFinal: false },
  { kind: 'zhihu', desc: '长文回答', needsFinal: false },
  { kind: 'wechat', desc: '排版好的文章，可推草稿箱', needsFinal: false },
  { kind: 'video', desc: '分镜、配音、字幕、成片', needsFinal: true },
  { kind: 'mv', desc: '歌词时间轴与画面', needsFinal: true },
  { kind: 'prompt_bundle', desc: '交给外部工具制作的提示词包', needsFinal: true },
];

const LAMP: Record<string, LampTone> = { draft: 'off', rendering: 'run', done: 'ok', failed: 'bad', exported: 'ok', published: 'ok' };

export default function OutputsIndex() {
  const router = useRouter();
  const { project } = useProject();
  const { items, reload } = useOutputs();
  const [busy, setBusy] = useState<OutputKind | null>(null);
  if (!project) return null;
  const final = Boolean(project.finalized_version);
  const create = async (kind: OutputKind) => {
    setBusy(kind);
    try {
      const o = await projectsApi.createOutput(project.id, kind);
      await reload();
      router.push(`/projects/${project.id}/outputs/${o.id}`);
    } catch (err) {
      toast.error(apiError(err, '新建失败'));
      setBusy(null);
    }
  };
  return (
    <div className="cw-outgrid-wrap">
      {!final ? (
        <EmptyInstrument
          compact
          kind="flat"
          title="定稿后可以做视频、MV 和提示词包"
          reason="平台版本可以先建草稿；讲解视频、音乐 MV、提示词包都基于定稿文案。"
          actions={
            <Link className="cw-btn" data-variant="primary" href={`/projects/${project.id}/draft`}>
              去定稿
            </Link>
          }
        />
      ) : null}
      <div className="cw-outgrid cw-stagger">
        {KINDS.map(({ kind, desc, needsFinal }) => {
          const mine = items.filter((o) => o.kind === kind);
          const locked = needsFinal && !final;
          if (!mine.length) {
            return (
              <button
                key={kind}
                type="button"
                className="cw-outtile"
                data-empty="true"
                disabled={locked || busy !== null}
                style={{ '--c': kindColor(kind) } as CSSProperties}
                onClick={() => create(kind)}
                title={locked ? '先定稿' : undefined}
              >
                <span className="cw-outtile-plus">
                  <Plus size={16} />
                </span>
                <b>{OUTPUT_LABEL[kind]}</b>
                <small>{locked ? '定稿后可做' : busy === kind ? '新建中…' : desc}</small>
              </button>
            );
          }
          return mine.map((o) => {
            const [label] = OUTPUT_STATUS[o.status] || [o.status];
            return (
              <Link key={o.id} href={`/projects/${project.id}/outputs/${o.id}`} className="cw-outtile" data-art-host style={{ '--c': kindColor(kind) } as CSSProperties}>
                <div className="cw-outtile-art">
                  <SignalArt title={o.title || project.title} kind={kind} />
                </div>
                <b>{OUTPUT_LABEL[kind]}</b>
                <small>
                  <StatusLamp tone={o.stale ? 'warn' : LAMP[o.status] || 'off'} label={o.stale ? '定稿已更新' : label} />
                  {o.based_on_version ? <span className="cw-num">v{o.based_on_version}</span> : null}
                </small>
              </Link>
            );
          });
        })}
      </div>
    </div>
  );
}
