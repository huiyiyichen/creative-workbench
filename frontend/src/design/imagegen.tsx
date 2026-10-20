'use client';

/** 生图面板（创作工作台设计 6.5）：参考 → 提示词（AI 起草）→ 服务 / 尺寸 / 张数 → 候选 → 出变体 / 以此为参考再生成 / 存入并使用。 */

import Link from 'next/link';
import { InputNumber, Input, Modal, Select, message } from 'antd';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Button } from './components';
import { AssetPicker, apiError } from './studio';
import { libraryApi, libraryFileUrl, type LibraryItem } from '@/lib/api/_library';
import { defaultAspect, genApi, targetLabel, type Aspect, type GenJob, type GenService, type GenTarget } from '@/lib/api/_generations';

const ASPECTS: Aspect[] = ['1:1', '3:4', '4:3', '16:9', '9:16'];

interface RefChip {
  id: number;
  title: string;
  thumb: boolean;
}

export function ImageGenPanel({
  open,
  onClose,
  projectId,
  outputId,
  target,
  defaultRefIds = [],
  styleId,
  onKept,
}: {
  open: boolean;
  onClose: () => void;
  projectId?: number | null;
  outputId?: number | null;
  target: GenTarget;
  defaultRefIds?: number[];
  styleId?: string | null;
  onKept?: (libraryItemIds: number[]) => void;
}) {
  const [services, setServices] = useState<GenService[] | null>(null);
  const [serviceId, setServiceId] = useState<number | undefined>();
  const [refs, setRefs] = useState<RefChip[]>([]);
  const [prompt, setPrompt] = useState('');
  const [aspect, setAspect] = useState<Aspect>(defaultAspect(target));
  const [n, setN] = useState(4);
  const [job, setJob] = useState<GenJob | null>(null);
  const [picked, setPicked] = useState<number[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [pickOpen, setPickOpen] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!open) return;
    setAspect(defaultAspect(target));
    setJob(null);
    setPicked([]);
    genApi
      .services('image')
      .then((r) => {
        const usable = r.items.filter((s) => s.enabled);
        setServices(usable);
        setServiceId((cur) => cur ?? usable[0]?.id);
      })
      .catch(() => setServices([]));
    Promise.all(defaultRefIds.map((id) => libraryApi.item(id).catch(() => null))).then((items) =>
      setRefs(items.filter(Boolean).map((it) => ({ id: it!.id, title: it!.title, thumb: Boolean(it!.thumb) }))),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const poll = useCallback((id: number) => {
    const tick = async () => {
      try {
        const j = await genApi.job(id);
        setJob(j);
        if (j.status === 'queued' || j.status === 'running') timer.current = setTimeout(tick, 1500);
        else if (j.status === 'failed') message.error(j.error || '生成失败');
      } catch {
        timer.current = setTimeout(tick, 4000);
      }
    };
    void tick();
  }, []);
  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);

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
  const service = services?.find((s) => s.id === serviceId);
  const draft = () =>
    guard('draft', async () => {
      const r = await genApi.draftPrompt(projectId ?? null, { target, style_id: styleId, ref_item_ids: refs.map((r) => r.id) });
      setPrompt(r.prompt);
    });
  const generate = (parent?: { job: number; index: number }) =>
    guard('gen', async () => {
      const j = await genApi.generate({
        prompt,
        ref_item_ids: refs.map((r) => r.id),
        aspect,
        n,
        service_id: serviceId,
        project_id: projectId ?? undefined,
        output_id: outputId ?? undefined,
        target,
        ...(parent ? { parent_job_id: parent.job, parent_index: parent.index } : {}),
      });
      setJob(j);
      setPicked([]);
      poll(j.id);
    });
  const keep = () =>
    guard('keep', async () => {
      if (!job || !picked.length) return;
      const r = await genApi.keep(job.id, picked);
      message.success(`已存入灵感库 ${r.library_item_ids.length} 张${projectId ? '，并加入项目素材' : ''}`);
      setJob(r.job);
      onKept?.(r.library_item_ids);
    });
  const running = job?.status === 'queued' || job?.status === 'running';
  const est = service ? service.unit_price * n : 0;

  return (
    <Modal open={open} onCancel={onClose} footer={null} width={880} title={`生图：${targetLabel(target)}`} destroyOnHidden>
      {services && !services.length ? (
        <div className="cw-notice" data-tone="warn">
          还没有可用的生成服务。
          <Link className="cw-link-btn" href="/settings/generation">
            配置生成服务
          </Link>
        </div>
      ) : null}
      <div className="cw-gen">
        <div className="cw-gen-row">
          <span className="cw-gen-label">参考</span>
          <div className="cw-gen-refs">
            {refs.map((r) => (
              <span key={r.id} className="cw-gen-ref" title={r.title}>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                {r.thumb ? <img src={libraryFileUrl(r.id, 'small')} alt="" /> : null}
                <small>{r.title.slice(0, 10)}</small>
                <button type="button" aria-label="移除参考" onClick={() => setRefs(refs.filter((x) => x.id !== r.id))}>
                  ×
                </button>
              </span>
            ))}
            <Button onClick={() => setPickOpen(true)}>+ 从灵感库</Button>
          </div>
        </div>
        {service && refs.length && !service.capabilities.refs ? (
          <p className="cw-muted" style={{ fontSize: 12, margin: 0 }}>
            这个服务不收参考图：参考条目的描述会写进提示词。
          </p>
        ) : null}
        <div className="cw-gen-row" style={{ alignItems: 'flex-start' }}>
          <span className="cw-gen-label">提示词</span>
          <div style={{ flex: 1 }}>
            <Input.TextArea value={prompt} onChange={(e) => setPrompt(e.target.value)} autoSize={{ minRows: 3, maxRows: 8 }} maxLength={8000} />
            <div className="cw-row" style={{ marginTop: 6 }}>
              <Button onClick={draft} disabled={busy !== null}>
                {busy === 'draft' ? '起草中…' : 'AI 起草 ↻'}
              </Button>
            </div>
          </div>
        </div>
        <div className="cw-gen-row">
          <span className="cw-gen-label">服务</span>
          <Select
            style={{ minWidth: 180 }}
            value={serviceId}
            onChange={setServiceId}
            options={(services || []).map((s) => ({ value: s.id, label: `${s.name}（${s.model}）` }))}
          />
          <span className="cw-gen-label">尺寸</span>
          <Select style={{ width: 90 }} value={aspect} onChange={setAspect} options={ASPECTS.map((a) => ({ value: a, label: a }))} />
          <span className="cw-gen-label">张数</span>
          <InputNumber min={1} max={service?.capabilities.max_n || 4} value={n} onChange={(v) => setN(Number(v) || 1)} style={{ width: 70 }} />
          <span className="cw-grow" />
          {service ? (
            <small className="cw-muted cw-num">
              预计 ¥{est.toFixed(2)} · 今日已用 ¥{service.spent_today.toFixed(2)}
              {service.daily_limit != null ? ` / ¥${service.daily_limit.toFixed(2)}` : ''}
            </small>
          ) : null}
          <Button variant="primary" onClick={() => generate()} disabled={!prompt.trim() || !service || busy !== null || running}>
            {running ? '生成中…' : '生成'}
          </Button>
        </div>
        {job ? (
          <div className="cw-gen-results" aria-live="polite">
            {Array.from({ length: job.params.n || job.results.length || 1 }).map((_, i) => {
              const r = job.results.find((x) => x.index === i);
              const on = picked.includes(i);
              return (
                <button
                  type="button"
                  key={i}
                  className="cw-gen-cand"
                  data-on={on || undefined}
                  data-kept={r?.library_item_id ? true : undefined}
                  disabled={!r}
                  onClick={() => setPicked(on ? picked.filter((x) => x !== i) : [...picked, i])}
                  style={{ aspectRatio: aspect.replace(':', ' / ') }}
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  {r ? <img src={genApi.fileUrl(r.url)} alt={`候选 ${i + 1}`} /> : <span className="cw-muted">{job.status === 'failed' ? '失败' : '生成中…'}</span>}
                  {on ? <b>✓</b> : null}
                  {r?.library_item_id ? <small>已存入</small> : null}
                </button>
              );
            })}
          </div>
        ) : null}
        {job?.status === 'failed' ? <div className="cw-error">{job.error}</div> : null}
        {job?.status === 'done' ? (
          <div className="cw-row">
            <span className="cw-muted cw-num">花费 ¥{job.cost.toFixed(2)}</span>
            <span className="cw-grow" />
            <Button onClick={() => picked[0] !== undefined && generate({ job: job.id, index: picked[0] })} disabled={picked.length !== 1 || busy !== null}>
              出变体
            </Button>
            <Button
              onClick={() =>
                guard('ref', async () => {
                  if (picked.length !== 1) return;
                  const r = await genApi.keep(job.id, picked);
                  const id = r.library_item_ids[0];
                  setRefs([{ id, title: '选中的生成图', thumb: true }, ...refs.filter((x) => x.id !== id)]);
                  setJob(r.job);
                  message.success('已设为参考，改提示词后再生成');
                })
              }
              disabled={picked.length !== 1 || busy !== null}
            >
              以此为参考再生成
            </Button>
            <Button variant="primary" onClick={keep} disabled={!picked.length || busy !== null}>
              存入并使用
            </Button>
          </div>
        ) : null}
      </div>
      <AssetPicker
        open={pickOpen}
        onClose={() => setPickOpen(false)}
        title="选参考（图片、风格、提示词）"
        exclude={refs.map((r) => r.id)}
        onPick={(items: LibraryItem[]) => {
          setRefs([...refs, ...items.map((it) => ({ id: it.id, title: it.title, thumb: it.thumb }))].slice(0, 8));
          setPickOpen(false);
        }}
      />
    </Modal>
  );
}
