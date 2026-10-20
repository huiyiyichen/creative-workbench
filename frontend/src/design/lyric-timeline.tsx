'use client';

/**
 * 歌词时间轴 LyricTimeline（创作工作台设计 5.1 MV 形态）：音频波形（wavesurfer.js）+ LRC 歌词点 + 分镜边界。
 * 拖动分镜边界时吸附到附近的歌词时间点；LRC 是歌词时间的唯一来源，这里只读歌词、不改歌词。
 */

import { Input, Modal, message } from 'antd';
import { Pause, Play, Upload, ZoomIn, ZoomOut } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import WaveSurfer from 'wavesurfer.js';
import RegionsPlugin from 'wavesurfer.js/dist/plugins/regions.esm.js';
import { Button } from './components';
import { apiError } from './studio';
import { projectsApi, type ProjectAudio, type Shot } from '@/lib/api/_projects';
import { boundaries, cueAt, moveBoundary, shotAt } from '@/lib/mv';

function cssVar(name: string, fallback: string): string {
  if (typeof window === 'undefined') return fallback;
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

function clock(t: number): string {
  const m = Math.floor(t / 60);
  const s = t - m * 60;
  return `${m}:${s.toFixed(1).padStart(4, '0')}`;
}

export function LyricTimeline({
  projectId,
  shots,
  cues,
  readOnly,
  selected,
  onSelect,
  onShots,
  onReload,
  onBefore,
}: {
  projectId: number;
  shots: Shot[];
  cues: { time: number; text: string }[];
  readOnly?: boolean;
  selected?: number[];
  onSelect?: (idx: number[]) => void;
  onShots: (shots: Shot[]) => void;
  onReload: () => Promise<void> | void;
  /** 服务端改文稿前先把本地未保存的修改存掉 */
  onBefore?: () => Promise<unknown>;
}) {
  const [audio, setAudio] = useState<ProjectAudio | null | undefined>(undefined);
  const [busy, setBusy] = useState<string | null>(null);
  const [lrcOpen, setLrcOpen] = useState(false);
  const [lrc, setLrc] = useState('');
  const [playing, setPlaying] = useState(false);
  const [now, setNow] = useState(0);
  const [ready, setReady] = useState(false);
  const [zoom, setZoom] = useState(0); // 每秒像素，0 = 铺满宽度
  const selfSelect = useRef(false);
  const linesRef = useRef<HTMLOListElement | null>(null);
  const box = useRef<HTMLDivElement | null>(null);
  const ws = useRef<WaveSurfer | null>(null);
  const regions = useRef<ReturnType<typeof RegionsPlugin.create> | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);
  const latest = useRef({ shots, cues, onShots, readOnly });
  useEffect(() => {
    latest.current = { shots, cues, onShots, readOnly };
  });

  useEffect(() => {
    projectsApi
      .audio(projectId)
      .then((r) => setAudio(r.audio))
      .catch(() => setAudio(null));
  }, [projectId]);

  // 波形
  useEffect(() => {
    if (!audio || !box.current) return;
    const plugin = RegionsPlugin.create();
    const w = WaveSurfer.create({
      container: box.current,
      url: projectsApi.audioUrl(audio),
      height: 76,
      waveColor: cssVar('--cw-line', '#333b48'),
      progressColor: cssVar('--cw-dim', '#8d96a3'),
      cursorColor: cssVar('--cw-text', '#e8eaed'),
      barWidth: 2,
      barGap: 1,
      normalize: true,
      plugins: [plugin],
      fetchParams: { credentials: 'include' },
    });
    ws.current = w;
    regions.current = plugin;
    w.on('ready', () => setReady(true));
    w.on('play', () => setPlaying(true));
    w.on('pause', () => setPlaying(false));
    w.on('timeupdate', (t) => setNow(t));
    plugin.on('region-updated', (region) => {
      const m = /^b-(\d+)$/.exec(region.id);
      if (!m) return;
      const { shots: cur, cues: cs, onShots: set } = latest.current;
      set(moveBoundary(cur, Number(m[1]), region.start, cs));
    });
    return () => {
      setReady(false);
      w.destroy();
      ws.current = null;
      regions.current = null;
    };
  }, [audio]);

  // 歌词点与分镜边界
  useEffect(() => {
    const plugin = regions.current;
    if (!plugin || !ready) return;
    plugin.clearRegions();
    const yl = cssVar('--cw-yl', '#e3cc4b');
    const cy = cssVar('--cw-cy', '#4fd2e2');
    for (const c of cues) {
      const tag = document.createElement('span');
      tag.style.cssText = `position:absolute;top:2px;left:4px;font-size:10px;line-height:1.2;white-space:nowrap;color:${yl};pointer-events:none;`;
      tag.textContent = c.text.split('\n')[0].slice(0, 14);
      plugin.addRegion({ id: `c-${c.time}`, start: c.time, color: yl, drag: false, resize: false, content: tag });
    }
    const b = boundaries(shots);
    for (let i = 1; i < shots.length; i++) {
      const tag = document.createElement('b');
      tag.style.cssText = `position:absolute;bottom:2px;left:4px;font-size:11px;font-weight:700;white-space:nowrap;color:${cy};pointer-events:none;`;
      tag.title = `第 ${i + 1} 镜起点，拖动调整（吸附歌词）`;
      tag.textContent = `▸${i + 1}`;
      plugin.addRegion({ id: `b-${i}`, start: b[i], color: cy, drag: !readOnly, resize: false, content: tag });
    }
  }, [shots, cues, ready, readOnly]);

  const uploadAudio = async (file: File) => {
    setBusy('audio');
    try {
      await onBefore?.();
      const r = await projectsApi.uploadAudio(projectId, file);
      setAudio(r.audio);
      message.success(`已上传，时长 ${clock(r.audio.duration || 0)}，分镜已按音频重排时长`);
      await onReload();
    } catch (err) {
      message.error(apiError(err));
    } finally {
      setBusy(null);
    }
  };
  const saveLrc = async () => {
    setBusy('lrc');
    try {
      await onBefore?.();
      const v = await projectsApi.setLrc(projectId, lrc);
      message.success(`歌词 ${v.draft.cues.length} 句，分镜边界已对齐歌词`);
      setLrcOpen(false);
      await onReload();
    } catch (err) {
      message.error(apiError(err));
    } finally {
      setBusy(null);
    }
  };
  const seek = (t: number) => {
    const w = ws.current;
    if (!w || !w.getDuration()) return;
    w.setTime(t);
  };
  const current = shots.length ? shotAt(shots, now) : -1;
  const nowCue = playing ? cueAt(cues, now) : -1;

  // 分镜表 / 大纲里选中某一镜（且没在播放）：波形跳到这一镜开头
  const selKey = (selected || []).join(',');
  useEffect(() => {
    if (selfSelect.current) {
      selfSelect.current = false;
      return;
    }
    const i = (selected || [])[0];
    const w = ws.current;
    if (i === undefined || !w || !ready || w.isPlaying() || !w.getDuration()) return;
    const b = boundaries(latest.current.shots);
    if (b[i] !== undefined) w.setTime(Math.min(b[i], w.getDuration()));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 只在选中项变化时跳
  }, [selKey, ready]);

  // 播放时当前歌词滚到可见
  useEffect(() => {
    if (nowCue < 0) return;
    const el = linesRef.current?.children[nowCue] as HTMLElement | undefined;
    el?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
  }, [nowCue]);

  useEffect(() => {
    const w = ws.current;
    if (!w || !ready) return;
    try {
      w.zoom(zoom);
    } catch {
      /* 音频未解码完时 zoom 会抛错，忽略 */
    }
  }, [zoom, ready]);

  return (
    <section className="cw-lyric" aria-label="歌词时间轴">
      <div className="cw-lyric-head">
        <strong>歌词时间轴</strong>
        {audio ? (
          <>
            <button type="button" className="cw-link-btn" onClick={() => ws.current?.playPause()} disabled={!ready} aria-label={playing ? '暂停' : '播放'}>
              {playing ? <Pause size={14} /> : <Play size={14} />}
            </button>
            <span className="cw-num cw-muted">
              {clock(now)} / {clock(audio.duration || 0)}
              {current >= 0 ? ` · 第 ${current + 1} 镜` : ''}
            </span>
            <span className="cw-muted" title={audio.name}>
              {audio.name}
            </span>
            <button type="button" className="cw-link-btn" onClick={() => setZoom((z) => Math.max(0, z ? (z <= 20 ? 0 : z / 2) : 0))} disabled={!ready || !zoom} aria-label="缩小波形" title="缩小">
              <ZoomOut size={14} />
            </button>
            <button type="button" className="cw-link-btn" onClick={() => setZoom((z) => Math.min(640, z ? z * 2 : 40))} disabled={!ready || zoom >= 640} aria-label="放大波形" title="放大">
              <ZoomIn size={14} />
            </button>
          </>
        ) : (
          <span className="cw-muted">{audio === undefined ? '加载中…' : '还没有音频：上传后波形和歌词会出现在这里'}</span>
        )}
        <span className="cw-grow" />
        {!readOnly ? (
          <>
            <input
              ref={fileRef}
              type="file"
              accept=".mp3,.wav,.m4a,.ogg,.flac,audio/*"
              hidden
              onChange={(e) => {
                const f = e.target.files?.[0];
                e.target.value = '';
                if (f) void uploadAudio(f);
              }}
              aria-label="选择音频文件"
            />
            <Button icon={<Upload size={13} />} onClick={() => fileRef.current?.click()} disabled={busy !== null}>
              {busy === 'audio' ? '上传中…' : audio ? '换音频' : '上传音频'}
            </Button>
            <Button onClick={() => setLrcOpen(true)} disabled={busy !== null}>
              {cues.length ? `歌词 ${cues.length} 句` : '粘贴 LRC'}
            </Button>
          </>
        ) : null}
      </div>
      {audio ? <div ref={box} className="cw-wave" /> : null}
      {cues.length ? (
        <ol className="cw-lyric-lines" ref={linesRef}>
          {cues.map((c, i) => {
            const shot = shotAt(shots, c.time);
            return (
              <li key={`${c.time}-${i}`} data-active={(selected || []).includes(shot) || undefined} data-now={i === nowCue || undefined}>
                <button
                  type="button"
                  onClick={() => {
                    seek(c.time);
                    if ((selected || []).join(',') !== String(shot)) selfSelect.current = true;
                    onSelect?.([shot]);
                  }}
                >
                  <span className="cw-num">{clock(c.time)}</span> {c.text}
                </button>
              </li>
            );
          })}
        </ol>
      ) : null}
      <Modal
        title="LRC 歌词"
        open={lrcOpen}
        onCancel={() => setLrcOpen(false)}
        onOk={saveLrc}
        okText="保存"
        cancelText="取消"
        confirmLoading={busy === 'lrc'}
        okButtonProps={{ disabled: !lrc.trim() }}
      >
        <p className="cw-muted" style={{ fontSize: 12 }}>
          每行形如 [00:12.50]歌词；支持 [offset:±毫秒]。歌词时间以 LRC 为准，保存后分镜边界会对齐到歌词。
        </p>
        <Input.TextArea
          value={lrc}
          onChange={(e) => setLrc(e.target.value)}
          autoSize={{ minRows: 8, maxRows: 18 }}
          placeholder={'[00:12.50]第一句\n[00:16.20]第二句'}
          aria-label="LRC 歌词"
        />
        <input
          type="file"
          accept=".lrc,.txt,text/plain"
          style={{ marginTop: 8 }}
          onChange={async (e) => {
            const f = e.target.files?.[0];
            if (f) setLrc(await f.text());
          }}
          aria-label="上传 LRC 文件"
        />
      </Modal>
    </section>
  );
}
