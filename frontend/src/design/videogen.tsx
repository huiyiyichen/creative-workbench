'use client';

/** 视频生成（改造方案第 8 节）：给分镜生成短视频片段，可用该镜关键帧作首帧；异步任务，进任务中心，完成后存入并使用。 */

import { Input, Modal, Select, Switch, message } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import { Button, Card } from './components';
import { genApi, type GenJob, type GenService } from '@/lib/api/_generations';
import type { ProjectAsset } from '@/lib/api/_projects';
import { onTasksChanged } from '@/lib/events';

type Shot = { beat: string; visual: string; seconds: number; prompt?: string };
type Aspect = '16:9' | '9:16' | '1:1';

const JOB_STATUS: Record<GenJob['status'], string> = { queued: '排队中', running: '生成中', done: '完成', failed: '失败' };

export function VideoClipsCard({
  projectId,
  outputId,
  shots,
  keyframes,
  aspect,
  locked,
  onKept,
}: {
  projectId: number;
  outputId: number;
  shots: Shot[];
  keyframes: ProjectAsset[];
  aspect: Aspect;
  locked: boolean;
  onKept?: () => void;
}) {
  const [services, setServices] = useState<GenService[] | null>(null);
  const [jobs, setJobs] = useState<GenJob[]>([]);
  const [shot, setShot] = useState<number | null>(null);
  const [prompt, setPrompt] = useState('');
  const [useFrame, setUseFrame] = useState(true);
  const [duration, setDuration] = useState(4);
  const [serviceId, setServiceId] = useState<number | undefined>();
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    try {
      const r = await genApi.jobs(projectId);
      setJobs(r.items.filter((j) => j.kind === 'video' && j.output_id === outputId));
    } catch {
      /* 不影响制作 */
    }
  }, [projectId, outputId]);
  useEffect(() => {
    genApi
      .services('video')
      .then((r) => {
        const ok = r.items.filter((s) => s.enabled);
        setServices(ok);
        const def = ok.find((s) => s.is_default) || ok[0];
        if (def) {
          setServiceId(def.id);
          setDuration((def.capabilities.durations || [4])[0]);
        }
      })
      .catch(() => setServices([]));
    void load();
  }, [load]);
  const active = jobs.some((j) => j.status === 'queued' || j.status === 'running');
  useEffect(() => {
    if (!active) return;
    const off = onTasksChanged(() => void load());
    const t = setInterval(() => void load(), 15_000);
    return () => {
      off();
      clearInterval(t);
    };
  }, [active, load]);
  if (!services || !services.length || !shots.length) return null;
  const service = services.find((s) => s.id === serviceId) || services[0];
  const durations = service.capabilities.durations || [4, 8, 12];
  const frameFor = (i: number) => keyframes.find((a) => a.role === 'keyframe' && (a.target as { shot?: number } | null)?.shot === i);
  const open = (i: number) => {
    const s = shots[i - 1];
    setShot(i);
    setPrompt([s.prompt || s.visual, s.beat].filter(Boolean).join('\n'));
    setUseFrame(Boolean(frameFor(i)));
    const want = Math.round(s.seconds || durations[0]);
    setDuration(durations.reduce((best, d) => (Math.abs(d - want) < Math.abs(best - want) ? d : best), durations[0]));
  };
  const submit = async () => {
    if (!shot) return;
    setBusy(true);
    try {
      const frame = frameFor(shot);
      await genApi.generateVideo({
        prompt,
        first_frame_item_id: useFrame && frame ? frame.library_item_id : null,
        duration,
        aspect,
        service_id: service.id,
        project_id: projectId,
        output_id: outputId,
        target: { type: 'shot', shot },
      });
      setShot(null);
      message.success('已提交，可以在任务里查看进度');
      await load();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '提交失败');
    } finally {
      setBusy(false);
    }
  };
  const keep = async (j: GenJob) => {
    try {
      await genApi.keep(j.id, [0], 'keyframe');
      message.success('已存入灵感库并挂到该镜头');
      onKept?.();
      await load();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '存入失败');
    }
  };
  return (
    <Card title="视频片段" extra={<small>用视频生成服务给分镜出短片段，可用关键帧作首帧</small>}>
      <div className="cw-row" style={{ flexWrap: 'wrap', gap: 6 }}>
        {shots.map((s, k) => (
          <Button key={k} onClick={() => open(k + 1)} disabled={locked}>
            第 {k + 1} 镜
          </Button>
        ))}
      </div>
      {jobs.length ? (
        <ul className="cw-clips">
          {jobs.map((j) => {
            const res = j.results[0];
            const shotNo = (j.target as { shot?: number } | null)?.shot;
            return (
              <li key={j.id} data-status={j.status}>
                {res ? <video src={genApi.fileUrl(res.url)} controls preload="metadata" /> : <div className="cw-clip-ph">{JOB_STATUS[j.status]}{j.status === 'running' && j.progress ? ` ${j.progress}%` : ''}</div>}
                <div className="cw-row" style={{ gap: 8, fontSize: 12 }}>
                  {shotNo ? <b className="cw-num">第 {shotNo} 镜</b> : null}
                  <span className="cw-num cw-muted">{j.params.seconds} 秒</span>
                  <span className="cw-muted">{JOB_STATUS[j.status]}</span>
                  {j.cost ? <span className="cw-num cw-muted">¥{j.cost.toFixed(2)}</span> : null}
                  <span className="cw-grow" />
                  {j.status === 'done' ? (
                    res?.library_item_id ? (
                      <span className="cw-muted">已存入</span>
                    ) : (
                      <button type="button" className="cw-link-btn" onClick={() => keep(j)}>
                        存入并使用
                      </button>
                    )
                  ) : null}
                </div>
                {j.error ? <small style={{ color: 'var(--cw-rd)' }}>{j.error}</small> : null}
              </li>
            );
          })}
        </ul>
      ) : null}
      <Modal
        title={shot ? `生成第 ${shot} 镜的视频片段` : ''}
        open={shot !== null}
        onCancel={() => setShot(null)}
        onOk={submit}
        okText={`生成（预计 ¥${(service.unit_price * duration).toFixed(2)}）`}
        cancelText="取消"
        confirmLoading={busy}
        okButtonProps={{ disabled: !prompt.trim() }}
      >
        <div className="cw-brief">
          {services.length > 1 ? (
            <label className="cw-brief-wide">
              <span>服务</span>
              <Select value={service.id} onChange={setServiceId} options={services.map((s) => ({ value: s.id, label: `${s.name} · ${s.model}` }))} />
            </label>
          ) : null}
          <label className="cw-brief-wide">
            <span>提示词</span>
            <Input.TextArea value={prompt} onChange={(e) => setPrompt(e.target.value)} autoSize={{ minRows: 3, maxRows: 8 }} maxLength={8000} />
          </label>
          <label>
            <span>时长（秒）</span>
            <Select value={duration} onChange={setDuration} options={durations.map((d) => ({ value: d, label: `${d} 秒` }))} />
          </label>
          <label>
            <span>画幅</span>
            <Input disabled value={`${aspect}（跟随制作参数）`} />
          </label>
          <label className="cw-inline cw-brief-wide">
            <Switch size="small" checked={useFrame && Boolean(shot && frameFor(shot))} disabled={!shot || !frameFor(shot) || service.capabilities.first_frame === false} onChange={setUseFrame} />
            {shot && frameFor(shot) ? '用这一镜的关键帧作首帧' : '这一镜还没有关键帧（可先在上面的分镜关键帧里生图）'}
          </label>
        </div>
      </Modal>
    </Card>
  );
}
