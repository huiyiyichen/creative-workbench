'use client';

/** 第一步：选题与创意（设计文档 4 节）——来源、已选来源、情绪板、创意方向、设定、开始写稿。 */

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Input, InputNumber, Select, message } from 'antd';
import { useEffect, useState } from 'react';
import { Button, Card } from '@/design/components';
import { MODE_LABEL, MoodBoard, SelectedSources, SourcePicker, apiError, useDirectionRun, useProject } from '@/design/studio';
import { projectsApi, type CopyBrief, type IdeaState, type ProjectMode } from '@/lib/api/_projects';

const VIDEO_MODES: ProjectMode[] = ['animation_video', 'video_prompt', 'music_video'];

export default function IdeaPage() {
  const { project, reload, setProject } = useProject();
  const router = useRouter();
  const [brief, setBrief] = useState<CopyBrief | null>(null);
  const [custom, setCustom] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const [dirAsk, setDirAsk] = useState(false);
  const run = useDirectionRun(project?.idea?.run_id);
  useEffect(() => {
    if (project && !brief) {
      setBrief(project.brief);
      setCustom(project.idea?.custom || '');
    }
  }, [project, brief]);
  if (!project || !brief) return null;
  const locked = Boolean(project.finalized_version);
  const set = <K extends keyof CopyBrief>(k: K, v: CopyBrief[K]) => setBrief({ ...brief, [k]: v });
  const save = async (next: CopyBrief = brief, idea?: IdeaState) => {
    const p = await projectsApi.saveBrief(project.id, next, idea ?? { ...project.idea, custom });
    setProject(p);
    return p;
  };
  const guard = async (key: string, fn: () => Promise<void>) => {
    setBusy(key);
    try {
      await fn();
    } catch (err) {
      message.error(apiError(err));
    } finally {
      setBusy(null);
    }
  };
  const pickDirection = (card: { id: string; title: string; angle: string; why_now?: string }) => {
    const next = { ...brief, theme: card.title, intent: [card.angle, card.why_now].filter(Boolean).join('\n') };
    setBrief(next);
    void guard('dir', async () => {
      await save(next, { ...project.idea, chosen: card.id, custom });
    });
  };
  const askDirections = () =>
    guard('directions', async () => {
      if (brief.theme !== project.brief.theme || brief.intent !== project.brief.intent) await save();
      await projectsApi.directions(project.id);
      await reload();
      setDirAsk(true);
    });
  const start = (mode: 'blank' | 'template') =>
    guard(mode, async () => {
      if (!brief.theme.trim()) throw new Error('先写一个主题');
      await save();
      await projectsApi.generate(project.id, mode);
      await reload();
      router.push(`/projects/${project.id}/draft`);
    });
  const empty = !project.sources.length && !brief.theme;
  return (
    <div className="cw-idea">
      {empty ? (
        <div className="cw-notice">从灵感库挑一条来源，或者在「手动输入」里直接写主题。</div>
      ) : null}
      <SourcePicker
        project={project}
        onChanged={() => void reload()}
        onManual={(t) => {
          const next = { ...brief, theme: t };
          setBrief(next);
          void guard('manual', async () => {
            await save(next);
          });
        }}
      />
      <Card title="已选来源" extra={<small>1 个主来源，最多 9 个参考；进入项目时冻结快照</small>}>
        <SelectedSources project={project} onChanged={() => void reload()} />
      </Card>
      <Card title="情绪板" extra={<small>图片、风格、提示词、随笔；只作创意和生图参考，不进引用</small>}>
        <MoodBoard projectId={project.id} />
      </Card>
      <Card
        title="创意方向"
        extra={
          <span className="cw-row">
            {project.idea?.run_id ? (
              <Link className="cw-link-btn" href={`/runs/${project.idea.run_id}`}>
                查看过程
              </Link>
            ) : null}
            <Button onClick={askDirections} disabled={busy === 'directions' || locked}>
              {busy === 'directions' ? '启动中…' : 'AI 给出方向'}
            </Button>
          </span>
        }
      >
        {run && ['running', 'queued'].includes(run.status) ? <p className="cw-muted">研究员和策划在工作…（{run.status}）</p> : null}
        {run && run.status === 'failed' ? (
          <div className="cw-error">
            方向生成失败：{run.reason || '未知原因'}{' '}
            <button type="button" className="cw-link-btn" onClick={askDirections}>
              重试
            </button>
          </div>
        ) : null}
        <div className="cw-dircards">
          {(run?.cards || []).map((c) => (
            <button key={c.id} type="button" className="cw-dircard" aria-pressed={project.idea?.chosen === c.id} onClick={() => pickDirection(c)} disabled={locked}>
              <div className="cw-dircard-head">
                <b>{c.title}</b>
                {c.format ? <small className="cw-muted">{c.format}</small> : null}
              </div>
              <p>{c.angle}</p>
              {c.why_now ? <p className="cw-muted">{c.why_now}</p> : null}
              {c.refs?.length ? <p className="cw-muted">依据：{c.refs.join('、')}</p> : null}
            </button>
          ))}
          <div className="cw-dircard">
            <div className="cw-dircard-head">
              <b>自己写</b>
            </div>
            <Input.TextArea
              value={custom}
              onChange={(e) => setCustom(e.target.value)}
              autoSize={{ minRows: 3, maxRows: 6 }}
              placeholder="写下你的角度，点「用这个」填进设定"
              maxLength={1000}
              disabled={locked}
            />
            <Button size="default" style={{ marginTop: 8 }} disabled={!custom.trim() || locked} onClick={() => pickDirection({ id: 'custom', title: brief.theme || custom.split('\n')[0].slice(0, 120), angle: custom })}>
              用这个
            </Button>
          </div>
        </div>
        {dirAsk && !run?.cards?.length && run?.status === 'done' ? <p className="cw-muted">这次没有得到方向卡，可以重试或自己写。</p> : null}
      </Card>
      <Card title="设定" extra={locked ? <small>已定稿：修改需先在文稿页「继续修改」</small> : <small>全部属于文案层，定稿时锁定</small>}>
        <div className="cw-brief">
          <label className="cw-brief-wide">
            <span>主题</span>
            <Input value={brief.theme} onChange={(e) => set('theme', e.target.value)} maxLength={500} disabled={locked} />
          </label>
          <label>
            <span>内容形态</span>
            <Select
              value={brief.mode}
              onChange={(v) => set('mode', v)}
              disabled={locked}
              options={(Object.keys(MODE_LABEL) as ProjectMode[]).map((m) => ({ value: m, label: MODE_LABEL[m] }))}
            />
          </label>
          {VIDEO_MODES.includes(brief.mode) ? (
            <label>
              <span>时长（秒）</span>
              <InputNumber min={5} max={600} value={brief.duration_seconds} onChange={(v) => set('duration_seconds', Number(v) || 180)} disabled={locked} />
            </label>
          ) : null}
          <label>
            <span>受众</span>
            <Input value={brief.audience} onChange={(e) => set('audience', e.target.value)} maxLength={300} disabled={locked} />
          </label>
          <label>
            <span>语气</span>
            <Input value={brief.tone} onChange={(e) => set('tone', e.target.value)} maxLength={200} placeholder="例如：克制、口语" disabled={locked} />
          </label>
          <label className="cw-brief-wide">
            <span>创作思路</span>
            <Input.TextArea value={brief.intent} onChange={(e) => set('intent', e.target.value)} autoSize={{ minRows: 3, maxRows: 10 }} maxLength={5000} disabled={locked} />
          </label>
        </div>
        <div className="cw-row" style={{ justifyContent: 'flex-end', marginTop: 12 }}>
          <Button onClick={() => guard('save', async () => { await save(); message.success('已保存设定'); })} disabled={locked || busy !== null}>
            保存设定
          </Button>
          {project.stage !== 'idea' || project.version ? (
            <Link className="cw-btn" data-variant="primary" href={`/projects/${project.id}/draft`}>
              去文稿
            </Link>
          ) : (
            <>
              <Button onClick={() => start('blank')} disabled={busy !== null}>
                空白开始
              </Button>
              <Button onClick={() => start('template')} disabled={busy !== null}>
                按模板生成结构
              </Button>
              <Button variant="primary" disabled title="成稿流程（写手 → 审校 → 写手修改）接入后可用">
                AI 写初稿
              </Button>
            </>
          )}
        </div>
      </Card>
    </div>
  );
}
