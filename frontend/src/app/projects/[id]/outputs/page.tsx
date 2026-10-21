'use client';

/** 产出总览：每种产出一格（已有的显示状态，没有的可以直接新建），像一排通道。 */

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Plus } from 'lucide-react';
import { useEffect, useState, type CSSProperties } from 'react';
import { PlatformPreview } from '@/design/platform-preview';
import { toast } from '@/design/feedback';
import { EmptyInstrument, StatusLamp, type LampTone } from '@/design/instrument';
import { SignalArt, kindColor } from '@/design/signal-art';
import { OUTPUT_LABEL, OUTPUT_STATUS, apiError, useProject } from '@/design/studio';
import { projectsApi, type Draft, type OutputKind, type OutputView } from '@/lib/api/_projects';
import { useOutputs } from './_ctx';

const KINDS: { kind: OutputKind; desc: string; needsFinal: boolean }[] = [
  { kind: 'xhs', desc: '标题、正文、标签、封面文案', needsFinal: false },
  { kind: 'douyin', desc: '前三秒钩子、分镜口播、话题', needsFinal: false },
  { kind: 'bilibili', desc: '标题、口播稿、弹幕点、简介', needsFinal: false },
  { kind: 'zhihu', desc: '长文回答', needsFinal: false },
  { kind: 'wechat', desc: '排版好的文章，可推草稿箱', needsFinal: false },
  { kind: 'video', desc: '分镜、配音、字幕、成片', needsFinal: true },
  { kind: 'mv', desc: '歌词时间轴与画面', needsFinal: true },
  { kind: 'prompt_bundle', desc: '交给外部工具制作的提示词包', needsFinal: true },
];

const SOCIAL: OutputKind[] = ['xhs', 'douyin', 'bilibili'];

/** 同一份定稿 → 三个平台的样子，并排看（也是拉票时「前后对比」的素材）。 */
function TriCompare({ projectId, outputs }: { projectId: number; outputs: OutputView[] }) {
  const [draft, setDraft] = useState<Draft | null>(null);
  useEffect(() => {
    projectsApi
      .draft(projectId)
      .then((d) => setDraft(d.draft))
      .catch(() => setDraft(null));
  }, [projectId]);
  const picks = SOCIAL.map((k) => outputs.find((o) => o.kind === k && o.content?.body)).filter(Boolean) as OutputView[];
  if (picks.length < 2) return null;
  const words = (draft?.body || '').replace(/\s/g, '').length;
  return (
    <section className="cw-tri-wrap" aria-label="三平台对照">
      <header className="cw-section-head">
        <h3>同一份稿，{picks.length} 种腔调</h3>
        <small className="cw-muted">
          原稿 {words} 字{draft?.title ? ` ·「${draft.title}」` : ''}
        </small>
      </header>
      <div className="cw-tri">
        {picks.map((o) => (
          <section key={o.id}>
            <header>
              <b>{OUTPUT_LABEL[o.kind]}</b>
              <Link className="cw-link-btn" href={`/projects/${projectId}/outputs/${o.id}`}>
                编辑
              </Link>
            </header>
            <PlatformPreview kind={o.kind} c={o.content} />
          </section>
        ))}
      </div>
    </section>
  );
}

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
      <TriCompare projectId={project.id} outputs={items} />
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
