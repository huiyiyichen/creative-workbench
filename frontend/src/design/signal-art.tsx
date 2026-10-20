'use client';

import type { CSSProperties } from 'react';
import { ART_H, ART_W, artKind, artSpec } from '@/lib/signal-art';
import { mediaColor } from './tokens';

export function kindColor(kind: string | null | undefined): string {
  const k = artKind(kind);
  const map: Record<string, string> = {
    video: mediaColor.video,
    article: mediaColor.article,
    image: mediaColor.image,
    prompt: mediaColor.prompt,
    repo: mediaColor.repo,
    list: mediaColor.list,
    other: mediaColor.article,
  };
  return map[k];
}

/** 按标题生成的信号图（封面缺失时）。hover 时迹线会重新扫描一遍（.cw-art:hover）。 */
export function SignalArt({ title, kind, className = '' }: { title: string; kind?: string | null; className?: string }) {
  const k = artKind(kind);
  const spec = artSpec(title, k);
  return (
    <svg
      className={`cw-art ${className}`}
      data-kind={k}
      viewBox={`0 0 ${ART_W} ${ART_H}`}
      preserveAspectRatio="none"
      aria-hidden
      style={{ '--c': kindColor(kind) } as CSSProperties}
    >
      {[0.25, 0.5, 0.75].map((y) => (
        <line key={y} className="cw-art-grid" x1="0" x2={ART_W} y1={ART_H * y} y2={ART_H * y} />
      ))}
      {[0.2, 0.4, 0.6, 0.8].map((x) => (
        <line key={x} className="cw-art-grid" data-v="true" x1={ART_W * x} x2={ART_W * x} y1="0" y2={ART_H} />
      ))}
      {spec.rects.map((r, i) => (
        <rect key={`r${i}`} className="cw-art-rect" x={r.x} y={r.y} width={r.w} height={r.h} rx={Math.min(3, r.h / 2)} style={{ opacity: r.o }} />
      ))}
      {spec.lines.map((l, i) => (
        <line key={`l${i}`} className="cw-art-link" x1={l.x1} y1={l.y1} x2={l.x2} y2={l.y2} />
      ))}
      {spec.traces.map((t, i) => (
        <path key={`t${i}`} className="cw-art-trace" data-strong={t.strong ? 'true' : undefined} d={t.d} pathLength={1} />
      ))}
      {spec.traces
        .filter((t) => t.strong)
        .map((t, i) => {
          const m = /L([\d.]+),([\d.]+)$/.exec(t.d);
          return m ? <circle key={`e${i}`} className="cw-art-end" cx={m[1]} cy={m[2]} r={2} /> : null;
        })}
      {spec.dots.map((d, i) => (
        <circle key={`d${i}`} className="cw-art-dot" cx={d.x} cy={d.y} r={d.r} />
      ))}
      {spec.progress !== undefined ? (
        <g className="cw-art-progress">
          <line x1="0" x2={ART_W} y1={ART_H - 3} y2={ART_H - 3} />
          <line data-on="true" x1="0" x2={ART_W * spec.progress} y1={ART_H - 3} y2={ART_H - 3} />
          <line data-head="true" x1={ART_W * spec.progress} x2={ART_W * spec.progress} y1="6" y2={ART_H - 3} />
        </g>
      ) : null}
    </svg>
  );
}
